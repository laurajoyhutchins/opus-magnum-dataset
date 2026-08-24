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
from .path_safety import resolve_confined_path
from .payload import validate_payload_policy
from .release_inputs import CONFIG_NAMES, SCHEMA_FILES, load_release_inputs, sort_records
from .schema_resources import load_schema_resource

RELEASE_MANIFEST_FORMAT_VERSION = 2
COVERAGE_POLICIES = ("complete", "subset")
DERIVED_COVERAGE_FIELDS = (
    "puzzle_count",
    "candidate_solution_count",
    "verified_solution_count",
    "rejected_solution_count",
    "by_puzzle",
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
    coverage_policy: str
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
            "coverage_policy": self.coverage_policy,
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
            coverage_policy=value["coverage_policy"],
            release_metadata=dict(value["release_metadata"]),
            release_metadata_sha256=value["release_metadata_sha256"],
            configs=configs,
            logical_release_sha256=value["logical_release_sha256"],
        )

    def with_logical_hash(self) -> ReleaseManifest:
        return replace(self, logical_release_sha256=compute_logical_release_hash(self))


def split_for_collection(collection_id: str) -> str:
    return collection_id.replace("-", "_")


def _coverage_state(candidate_count: int, verified_count: int) -> str:
    if verified_count > 1:
        return "multi_solution"
    if verified_count == 1:
        return "verified"
    if candidate_count:
        return "candidate_found"
    return "uncovered"


def derive_release_coverage(
    collection: CollectionDefinition,
    records: dict[str, list[dict[str, Any]]],
    *,
    coverage_policy: str,
) -> dict[str, Any]:
    errors: list[ValidationError] = []
    if coverage_policy not in COVERAGE_POLICIES:
        errors.append(
            ValidationError(
                "coverage_policy_invalid",
                f"coverage_policy must be one of {COVERAGE_POLICIES}, got {coverage_policy!r}",
                "release-manifest.json",
            )
        )

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
    if unexpected or (coverage_policy == "complete" and missing):
        details: list[str] = []
        if missing and coverage_policy == "complete":
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

    solutions = records.get("solutions", [])
    by_puzzle: dict[str, dict[str, int | str]] = {}
    for puzzle_id in sorted(expected_puzzle_ids):
        puzzle_solutions = [row for row in solutions if row.get("puzzle_id") == puzzle_id]
        candidate_count = len(puzzle_solutions)
        verified_count = sum(row.get("verified") is True for row in puzzle_solutions)
        by_puzzle[puzzle_id] = {
            "candidate_solution_count": candidate_count,
            "verified_solution_count": verified_count,
            "rejected_solution_count": candidate_count - verified_count,
            "state": _coverage_state(candidate_count, verified_count),
        }

    if coverage_policy == "complete":
        unverified = sorted(
            puzzle_id
            for puzzle_id, puzzle_coverage in by_puzzle.items()
            if puzzle_coverage["verified_solution_count"] == 0
        )
        if unverified:
            errors.append(
                ValidationError(
                    "collection_verified_coverage_incomplete",
                    f"puzzles without a verified solution: {unverified}",
                    "solutions",
                )
            )

    if errors:
        raise ReleaseValidationError(errors)

    verified_count = sum(row.get("verified") is True for row in solutions)
    return {
        "puzzle_count": len(records.get("puzzles", [])),
        "candidate_solution_count": len(solutions),
        "verified_solution_count": verified_count,
        "rejected_solution_count": len(solutions) - verified_count,
        "by_puzzle": by_puzzle,
    }


def derive_release_metadata(
    collection: CollectionDefinition,
    records: dict[str, list[dict[str, Any]]],
    metadata: dict[str, Any],
    *,
    coverage_policy: str,
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
    derived = derive_release_coverage(
        collection,
        records,
        coverage_policy=coverage_policy,
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
        "coverage_policy": manifest.coverage_policy,
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
        metadata_only = row.get("source_role") == "metadata" and artifact_id is None
        if metadata_only:
            continue
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


def build_release(
    collection: CollectionDefinition,
    input_dir: Path,
    output_dir: Path,
    config: CorpusConfig,
    payload_policy: str,
    coverage_policy: str = "complete",
) -> ReleaseManifest:
    loaded = load_release_inputs(input_dir)
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
    release_metadata = derive_release_metadata(
        collection,
        loaded.records,
        release_metadata,
        coverage_policy=coverage_policy,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    split = split_for_collection(collection.collection_id)
    config_results: dict[str, ConfigRelease] = {}

    for config_name in CONFIG_NAMES:
        rows = loaded.records[config_name]
        parquet_rel = Path("data") / config_name / f"{split}-00000-of-00001.parquet"
        parquet_path = output_dir / parquet_rel
        write_parquet(config_name, rows, parquet_path, config)
        schema_resource = load_schema_resource(SCHEMA_FILES[config_name])
        source = loaded.sources[config_name]
        config_results[config_name] = ConfigRelease(
            schema_path=schema_resource.logical_path,
            schema_sha256=schema_resource.sha256,
            records_sha256=canonical_records_sha256(rows),
            row_count=len(rows),
            parquet_path=parquet_rel.as_posix(),
            parquet_sha256=sha256_file(parquet_path),
            source_path=source["path"],
            source_sha256=source["sha256"],
        )

    manifest = ReleaseManifest(
        format_version=RELEASE_MANIFEST_FORMAT_VERSION,
        corpus_schema_version=release_metadata["corpus_schema_version"],
        collection_id=collection.collection_id,
        collection_inventory_sha256=collection.inventory_sha256,
        split=split,
        build_software_revision=detect_git_revision(config.root),
        build_config_sha256=sha256_file(config.path),
        payload_policy=payload_policy,
        coverage_policy=coverage_policy,
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


def _ensure_supported_manifest_format(format_version: Any) -> None:
    if format_version != RELEASE_MANIFEST_FORMAT_VERSION:
        raise ReleaseValidationError(
            [
                ValidationError(
                    "release_manifest_format_unsupported",
                    f"unsupported format_version {format_version}; supported "
                    f"format_version is {RELEASE_MANIFEST_FORMAT_VERSION}",
                    "release-manifest.json",
                )
            ]
        )


def _read_manifest(output_dir: Path) -> ReleaseManifest:
    path = Path(output_dir) / "release-manifest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("manifest root must be an object")
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ReleaseValidationError(
            [ValidationError("release_manifest_invalid", str(exc), path.as_posix())]
        ) from exc

    if "format_version" in value:
        _ensure_supported_manifest_format(value["format_version"])

    try:
        return ReleaseManifest.from_dict(value)
    except (KeyError, TypeError) as exc:
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
    _ensure_supported_manifest_format(manifest.format_version)

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
    if manifest.coverage_policy not in COVERAGE_POLICIES:
        errors.append(
            ValidationError(
                "coverage_policy_invalid",
                f"coverage_policy must be one of {COVERAGE_POLICIES}",
                "release-manifest.json",
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
        schema_resource = load_schema_resource(SCHEMA_FILES[config_name])
        if schema_resource.sha256 != entry.schema_sha256:
            errors.append(
                ValidationError(
                    "schema_changed",
                    f"schema changed for {config_name}",
                    schema_resource.logical_path,
                )
            )
            continue
        try:
            parquet_path = resolve_confined_path(output_dir, entry.parquet_path)
        except ValueError as exc:
            errors.append(
                ValidationError(
                    "release_manifest_path_unsafe",
                    str(exc),
                    f"release-manifest.json#configs.{config_name}.parquet_path",
                )
            )
            continue
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
        try:
            _validate_rows(config_name, rows, schema_resource.schema)
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
                coverage_policy=manifest.coverage_policy,
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
