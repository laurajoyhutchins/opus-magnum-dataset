from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .collections import CollectionDefinition
from .config import CorpusConfig
from .errors import ReleaseValidationError, ValidationError
from .hashing import (
    canonical_json_bytes,
    canonical_records_sha256,
    sha256_bytes,
    sha256_file,
)
from .parquet import read_parquet, write_parquet
from .payload import validate_payload_policy
from .release_inputs import (
    CONFIG_NAMES,
    SCHEMA_FILES,
    load_release_inputs,
    load_schema,
    sort_records,
)

DERIVED_COVERAGE_FIELDS = (
    "puzzle_count",
    "candidate_solution_count",
    "verified_solution_count",
    "rejected_solution_count",
)
CANONICAL_ID_FIELDS = {
    "puzzles": "puzzle_id",
    "solutions": "solution_id",
    "observations": "observation_id",
    "normalized": "normalized_solution_id",
}


@dataclass(frozen=True)
class ConfigRelease:
    schema_path: str
    schema_sha256: str
    records_sha256: str
    row_count: int
    parquet_path: str
    parquet_sha256: str
    source_path: str
    source_sha256: str


@dataclass(frozen=True)
class ReleaseManifest:
    format_version: int
    corpus_schema_version: str
    collection_id: str
    collection_inventory_sha256: str
    split: str
    build_software_revision: str | None
    build_config_sha256: str
    payload_policy: str
    release_metadata: dict[str, Any]
    release_metadata_sha256: str
    configs: dict[str, ConfigRelease]
    logical_release_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "corpus_schema_version": self.corpus_schema_version,
            "collection_id": self.collection_id,
            "collection_inventory_sha256": self.collection_inventory_sha256,
            "split": self.split,
            "build_software_revision": self.build_software_revision,
            "build_config_sha256": self.build_config_sha256,
            "payload_policy": self.payload_policy,
            "release_metadata": self.release_metadata,
            "release_metadata_sha256": self.release_metadata_sha256,
            "configs": {
                name: asdict(value) for name, value in sorted(self.configs.items())
            },
            "logical_release_sha256": self.logical_release_sha256,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ReleaseManifest:
        configs = {
            name: ConfigRelease(**config_value)
            for name, config_value in value.get("configs", {}).items()
        }
        return cls(
            format_version=value["format_version"],
            corpus_schema_version=value["corpus_schema_version"],
            collection_id=value["collection_id"],
            collection_inventory_sha256=value["collection_inventory_sha256"],
            split=value["split"],
            build_software_revision=value.get("build_software_revision"),
            build_config_sha256=value["build_config_sha256"],
            payload_policy=value["payload_policy"],
            release_metadata=dict(value["release_metadata"]),
            release_metadata_sha256=value["release_metadata_sha256"],
            configs=configs,
            logical_release_sha256=value["logical_release_sha256"],
        )

    def with_logical_hash(self) -> ReleaseManifest:
        return replace(self, logical_release_sha256=compute_logical_release_hash(self))


def split_for_collection(collection_id: str) -> str:
    return collection_id.replace("-", "_")


def derive_release_coverage(
    collection: CollectionDefinition,
    records: dict[str, list[dict[str, Any]]],
    *,
    release_kind: str,
) -> dict[str, int]:
    errors: list[ValidationError] = []
    for config_name, identity_field in CANONICAL_ID_FIELDS.items():
        seen: dict[Any, int] = {}
        for index, row in enumerate(records.get(config_name, []), start=1):
            identity = row.get(identity_field)
            if identity is None:
                continue
            if identity in seen:
                errors.append(
                    ValidationError(
                        "duplicate_canonical_id",
                        f"duplicate {identity_field} {identity!r}; first seen on row "
                        f"{seen[identity]}",
                        config_name,
                        index,
                    )
                )
            else:
                seen[identity] = index

    expected_puzzle_ids = {
        row["puzzle_id"] for row in collection.inventory_rows if row.get("puzzle_id")
    }
    actual_puzzle_ids = {
        row.get("puzzle_id") for row in records.get("puzzles", []) if row.get("puzzle_id")
    }
    unexpected = sorted(actual_puzzle_ids - expected_puzzle_ids)
    missing = sorted(expected_puzzle_ids - actual_puzzle_ids)
    if release_kind == "fixture":
        if unexpected:
            errors.append(
                ValidationError(
                    "collection_coverage_mismatch",
                    f"fixture contains puzzles outside collection: {unexpected}",
                    "puzzles",
                )
            )
    elif missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing puzzles: {missing}")
        if unexpected:
            details.append(f"unexpected puzzles: {unexpected}")
        errors.append(
            ValidationError(
                "collection_coverage_mismatch",
                "; ".join(details),
                "puzzles",
            )
        )

    if errors:
        raise ReleaseValidationError(errors)

    solutions = records.get("solutions", [])
    verified_count = sum(row.get("verified") is True for row in solutions)
    return {
        "puzzle_count": len(records.get("puzzles", [])),
        "candidate_solution_count": len(solutions),
        "verified_solution_count": verified_count,
        "rejected_solution_count": len(solutions) - verified_count,
    }


def derive_release_metadata(
    collection: CollectionDefinition,
    records: dict[str, list[dict[str, Any]]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    coverage = metadata.get("coverage", {})
    if not isinstance(coverage, dict):
        raise ReleaseValidationError(
            [
                ValidationError(
                    "release_metadata_invalid",
                    "coverage must be an object when supplied",
                    "release-metadata.json",
                )
            ]
        )
    supplied = sorted(set(coverage) & set(DERIVED_COVERAGE_FIELDS))
    if supplied:
        raise ReleaseValidationError(
            [
                ValidationError(
                    "release_metadata_derived_field",
                    f"coverage fields are derived from canonical rows: {supplied}",
                    "release-metadata.json",
                )
            ]
        )
    release_kind = metadata.get("release_kind", "release")
    if not isinstance(release_kind, str) or not release_kind:
        raise ReleaseValidationError(
            [
                ValidationError(
                    "release_metadata_invalid",
                    "release_kind must be a non-empty string",
                    "release-metadata.json",
                )
            ]
        )
    derived = derive_release_coverage(
        collection,
        records,
        release_kind=release_kind,
    )
    result = dict(metadata)
    result["coverage"] = {**coverage, **derived}
    return result


def _logical_manifest_dict(manifest: ReleaseManifest) -> dict[str, Any]:
    return {
        "format_version": manifest.format_version,
        "corpus_schema_version": manifest.corpus_schema_version,
        "collection_id": manifest.collection_id,
        "collection_inventory_sha256": manifest.collection_inventory_sha256,
        "split": manifest.split,
        "build_software_revision": manifest.build_software_revision,
        "build_config_sha256": manifest.build_config_sha256,
        "payload_policy": manifest.payload_policy,
        "release_metadata": manifest.release_metadata,
        "release_metadata_sha256": manifest.release_metadata_sha256,
        "configs": {
            name: {
                "schema_path": value.schema_path,
                "schema_sha256": value.schema_sha256,
                "records_sha256": value.records_sha256,
                "row_count": value.row_count,
                "parquet_path": value.parquet_path,
                "source_path": value.source_path,
                "source_sha256": value.source_sha256,
            }
            for name, value in sorted(manifest.configs.items())
        },
    }


def compute_logical_release_hash(manifest: ReleaseManifest) -> str:
    return sha256_bytes(canonical_json_bytes(_logical_manifest_dict(manifest)))


def detect_git_revision(root: Path) -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision or None


def _validate_rows(
    config_name: str,
    rows: list[dict[str, Any]],
    schema: dict[str, Any],
) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[ValidationError] = []
    for index, row in enumerate(rows, start=1):
        row_errors = sorted(
            validator.iter_errors(row),
            key=lambda item: (list(item.path), item.message),
        )
        for error in row_errors:
            errors.append(
                ValidationError("schema_invalid", error.message, config_name, index)
            )
    if errors:
        raise ReleaseValidationError(errors)


def validate_referential_integrity(
    records: dict[str, list[dict[str, Any]]],
) -> None:
    puzzles = {row.get("puzzle_id") for row in records.get("puzzles", [])}
    puzzle_artifacts = {
        row.get("canonical_puzzle_artifact_id")
        for row in records.get("puzzles", [])
        if row.get("canonical_puzzle_artifact_id")
    }
    solutions = {row.get("solution_id") for row in records.get("solutions", [])}
    errors: list[ValidationError] = []
    for index, row in enumerate(records.get("solutions", []), start=1):
        if row.get("puzzle_id") not in puzzles:
            errors.append(
                ValidationError(
                    "referential_integrity",
                    f"solution {row.get('solution_id')} references unknown puzzle "
                    f"{row.get('puzzle_id')}",
                    "solutions",
                    index,
                )
            )
    for index, row in enumerate(records.get("normalized", []), start=1):
        if row.get("solution_id") not in solutions:
            errors.append(
                ValidationError(
                    "referential_integrity",
                    f"normalized row references unknown solution {row.get('solution_id')}",
                    "normalized",
                    index,
                )
            )
        if row.get("puzzle_id") not in puzzles:
            errors.append(
                ValidationError(
                    "referential_integrity",
                    f"normalized row references unknown puzzle {row.get('puzzle_id')}",
                    "normalized",
                    index,
                )
            )
    for index, row in enumerate(records.get("observations", []), start=1):
        artifact_kind = row.get("artifact_kind")
        artifact_id = row.get("artifact_id")
        if artifact_kind == "solution" and artifact_id not in solutions:
            errors.append(
                ValidationError(
                    "referential_integrity",
                    f"observation references unknown solution {artifact_id}",
                    "observations",
                    index,
                )
            )
        if artifact_kind == "puzzle" and artifact_id not in puzzle_artifacts:
            errors.append(
                ValidationError(
                    "referential_integrity",
                    f"observation references unknown puzzle artifact {artifact_id}",
                    "observations",
                    index,
                )
            )
    if errors:
        raise ReleaseValidationError(errors)


def _load_release_metadata(input_dir: Path) -> tuple[dict[str, Any], str]:
    path = Path(input_dir) / "release-metadata.json"
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError(
            [ValidationError("release_metadata_invalid", str(exc), path.as_posix())]
        ) from exc
    if not isinstance(value, dict) or not isinstance(
        value.get("corpus_schema_version"), str
    ):
        raise ReleaseValidationError(
            [
                ValidationError(
                    "release_metadata_invalid",
                    "release metadata must be an object with corpus_schema_version",
                    path.as_posix(),
                )
            ]
        )
    return value, sha256_bytes(raw)


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def build_release(
    collection: CollectionDefinition,
    input_dir: Path,
    output_dir: Path,
    config: CorpusConfig,
    payload_policy: str,
) -> ReleaseManifest:
    loaded = load_release_inputs(input_dir, config.schemas_dir)
    for config_name, rows in loaded.records.items():
        validate_payload_policy(config_name, rows, payload_policy)
    validate_referential_integrity(loaded.records)

    collection_errors: list[ValidationError] = []
    for config_name in ("puzzles", "solutions"):
        for index, row in enumerate(loaded.records[config_name], start=1):
            if row.get("collection_id") != collection.collection_id:
                collection_errors.append(
                    ValidationError(
                        "collection_mismatch",
                        f"row collection_id {row.get('collection_id')!r} != "
                        f"{collection.collection_id!r}",
                        config_name,
                        index,
                    )
                )
    if collection_errors:
        raise ReleaseValidationError(collection_errors)

    release_metadata, release_metadata_sha256 = _load_release_metadata(input_dir)
    release_metadata = derive_release_metadata(collection, loaded.records, release_metadata)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    split = split_for_collection(collection.collection_id)
    config_results: dict[str, ConfigRelease] = {}

    for config_name in CONFIG_NAMES:
        rows = loaded.records[config_name]
        parquet_rel = Path("data") / config_name / f"{split}-00000-of-00001.parquet"
        parquet_path = output_dir / parquet_rel
        write_parquet(config_name, rows, parquet_path, config)
        schema_path = config.schemas_dir / SCHEMA_FILES[config_name]
        source = loaded.sources[config_name]
        config_results[config_name] = ConfigRelease(
            schema_path=_safe_relative(schema_path, config.root),
            schema_sha256=sha256_file(schema_path),
            records_sha256=canonical_records_sha256(rows),
            row_count=len(rows),
            parquet_path=parquet_rel.as_posix(),
            parquet_sha256=sha256_file(parquet_path),
            source_path=source["path"],
            source_sha256=source["sha256"],
        )

    manifest = ReleaseManifest(
        format_version=1,
        corpus_schema_version=release_metadata["corpus_schema_version"],
        collection_id=collection.collection_id,
        collection_inventory_sha256=collection.inventory_sha256,
        split=split,
        build_software_revision=detect_git_revision(config.root),
        build_config_sha256=sha256_file(config.path),
        payload_policy=payload_policy,
        release_metadata=release_metadata,
        release_metadata_sha256=release_metadata_sha256,
        configs=config_results,
        logical_release_sha256="",
    ).with_logical_hash()
    manifest_path = output_dir / "release-manifest.json"
    temp_path = output_dir / ".release-manifest.json.tmp"
    temp_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(manifest_path)
    return manifest


def _read_manifest(output_dir: Path) -> ReleaseManifest:
    path = Path(output_dir) / "release-manifest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("manifest root must be an object")
        return ReleaseManifest.from_dict(value)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReleaseValidationError(
            [ValidationError("release_manifest_invalid", str(exc), path.as_posix())]
        ) from exc


def validate_release(
    collection: CollectionDefinition,
    output_dir: Path,
    config: CorpusConfig,
) -> ReleaseManifest:
    output_dir = Path(output_dir)
    manifest = _read_manifest(output_dir)
    errors: list[ValidationError] = []
    if manifest.collection_id != collection.collection_id:
        errors.append(
            ValidationError(
                "collection_mismatch",
                "manifest collection_id does not match",
                "release-manifest.json",
            )
        )
    if manifest.collection_inventory_sha256 != collection.inventory_sha256:
        errors.append(
            ValidationError(
                "collection_hash_mismatch",
                "collection inventory hash changed",
                "release-manifest.json",
            )
        )
    if manifest.build_config_sha256 != sha256_file(config.path):
        errors.append(
            ValidationError(
                "build_config_changed",
                "build configuration changed since release",
                config.path.as_posix(),
            )
        )
    if set(manifest.configs) != set(CONFIG_NAMES):
        errors.append(
            ValidationError(
                "release_configs_invalid",
                "release must contain all four canonical configs",
                "release-manifest.json",
            )
        )
    if errors:
        raise ReleaseValidationError(errors)

    records: dict[str, list[dict[str, Any]]] = {}
    for config_name in CONFIG_NAMES:
        entry = manifest.configs[config_name]
        schema_path = config.schemas_dir / SCHEMA_FILES[config_name]
        if sha256_file(schema_path) != entry.schema_sha256:
            errors.append(
                ValidationError(
                    "schema_changed",
                    f"schema changed for {config_name}",
                    schema_path.as_posix(),
                )
            )
            continue
        parquet_path = output_dir / entry.parquet_path
        if not parquet_path.is_file():
            errors.append(
                ValidationError(
                    "parquet_missing",
                    f"missing {entry.parquet_path}",
                    parquet_path.as_posix(),
                )
            )
            continue
        if sha256_file(parquet_path) != entry.parquet_sha256:
            errors.append(
                ValidationError(
                    "parquet_hash_mismatch",
                    f"bytes changed for {config_name}",
                    parquet_path.as_posix(),
                )
            )
            continue
        rows = sort_records(config_name, read_parquet(config_name, parquet_path))
        schema = load_schema(config.schemas_dir, config_name)
        try:
            _validate_rows(config_name, rows, schema)
            validate_payload_policy(config_name, rows, manifest.payload_policy)
        except ReleaseValidationError as exc:
            errors.extend(exc.errors)
            continue
        if canonical_records_sha256(rows) != entry.records_sha256:
            errors.append(
                ValidationError(
                    "records_hash_mismatch",
                    f"logical rows changed for {config_name}",
                    parquet_path.as_posix(),
                )
            )
        if len(rows) != entry.row_count:
            errors.append(
                ValidationError(
                    "row_count_mismatch",
                    f"row count changed for {config_name}",
                    parquet_path.as_posix(),
                )
            )
        records[config_name] = rows

    if not errors:
        try:
            validate_referential_integrity(records)
            expected_coverage = derive_release_coverage(
                collection,
                records,
                release_kind=str(manifest.release_metadata.get("release_kind", "release")),
            )
            stored_coverage = manifest.release_metadata.get("coverage")
            if not isinstance(stored_coverage, dict):
                errors.append(
                    ValidationError(
                        "release_coverage_mismatch",
                        "manifest release metadata has no coverage object",
                        "release-manifest.json",
                    )
                )
            else:
                for field, expected in expected_coverage.items():
                    if stored_coverage.get(field) != expected:
                        errors.append(
                            ValidationError(
                                "release_coverage_mismatch",
                                f"{field} expected {expected}, got {stored_coverage.get(field)!r}",
                                "release-manifest.json",
                            )
                        )
        except ReleaseValidationError as exc:
            errors.extend(exc.errors)
    if compute_logical_release_hash(manifest) != manifest.logical_release_sha256:
        errors.append(
            ValidationError(
                "logical_release_hash_mismatch",
                "logical release hash does not match manifest",
                "release-manifest.json",
            )
        )
    if errors:
        raise ReleaseValidationError(errors)
    return manifest
