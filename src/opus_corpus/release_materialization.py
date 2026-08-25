from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .collections import CollectionDefinition
from .content_store import ContentStore, ContentStoreError
from .errors import CorpusError
from .hashing import canonical_json_bytes, sha256_bytes
from .normalization import normalized_solution_id
from .payload import validate_payload_policy
from .release_configs import CONFIG_NAMES
from .release_inputs import load_schema, sort_records
from .schema_resources import load_schema_resource
from .verification import verification_id

RELEASE_MATERIALIZER_VERSION = "release-materializer-v1"
_DERIVED_RELEASE_METADATA_FIELDS = frozenset(
    {
        "verifier_revision",
        "verifier_sha256",
        "validation_profile",
        "normalizer_version",
        "source_classes",
    }
)


class ReleaseMaterializationError(CorpusError):
    """Raised when canonical entities cannot be projected unambiguously."""


def _mapping(value: object, *, label: str) -> dict[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        result = asdict(value)
    elif isinstance(value, Mapping):
        result = dict(value)
    else:
        raise ReleaseMaterializationError(
            f"{label} must be a mapping or dataclass record"
        )
    return result


def _unique_by(
    values: Iterable[object],
    field: str,
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        row = _mapping(value, label=label)
        identity = row.get(field)
        if not isinstance(identity, str) or not identity:
            raise ReleaseMaterializationError(f"{label} has invalid {field}")
        if identity in result:
            raise ReleaseMaterializationError(
                f"duplicate {label} {field} {identity!r}"
            )
        result[identity] = row
    return result


def _validate_artifact(row: Mapping[str, Any], *, kind: str) -> None:
    if row.get("artifact_kind") != kind:
        raise ReleaseMaterializationError(
            f"{row.get('artifact_id')}: expected {kind} artifact, "
            f"got {row.get('artifact_kind')!r}"
        )
    if row.get("artifact_format") != kind:
        raise ReleaseMaterializationError(
            f"{row.get('artifact_id')}: expected {kind} format, "
            f"got {row.get('artifact_format')!r}"
        )
    digest = row.get("sha256")
    if not isinstance(digest, str):
        raise ReleaseMaterializationError(
            f"{row.get('artifact_id')}: artifact sha256 is invalid"
        )
    prefix = "om.puzzle-artifact.sha256." if kind == "puzzle" else "om.solution.sha256."
    if row.get("artifact_id") != prefix + digest:
        raise ReleaseMaterializationError(
            f"{row.get('artifact_id')}: artifact identity does not match sha256"
        )
    expected_object_key = f"objects/sha256/{digest[:2]}/{digest[2:]}"
    if row.get("object_key") != expected_object_key:
        raise ReleaseMaterializationError(
            f"{row.get('artifact_id')}: artifact object identity does not match sha256"
        )


def _validate_verification(row: Mapping[str, Any]) -> None:
    schema = load_schema_resource("verification.schema.json").schema
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(dict(row)),
        key=lambda error: (list(error.path), error.message),
    )
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise ReleaseMaterializationError(
            f"Verification record violates the canonical schema: {detail}"
        )
    expected_id = verification_id(
        puzzle_artifact_id=row["puzzle_artifact_id"],
        solution_id=row["solution_id"],
        verifier_implementation=row["verifier_implementation"],
        verifier_revision=row["verifier_revision"],
        verifier_sha256=row["verifier_sha256"],
        validation_profile=row["validation_profile"],
    )
    if row["verification_id"] != expected_id:
        raise ReleaseMaterializationError(
            "Verification identity does not match canonical verifier inputs"
        )


def _validate_normalized_identity(row: Mapping[str, Any]) -> None:
    expected_id = normalized_solution_id(
        solution_id=row["solution_id"],
        puzzle_id=row["puzzle_id"],
        normalizer_version=row["normalizer_version"],
    )
    if row.get("normalized_solution_id") != expected_id:
        raise ReleaseMaterializationError(
            "normalized solution identity does not match canonical normalization inputs"
        )


def _collection_rows(collection: CollectionDefinition) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for row in collection.inventory_rows:
        puzzle_id = row.get("puzzle_id")
        if not isinstance(puzzle_id, str) or not puzzle_id:
            raise ReleaseMaterializationError("collection contains an invalid puzzle_id")
        if puzzle_id in rows:
            raise ReleaseMaterializationError(
                f"duplicate collection puzzle_id {puzzle_id!r}"
            )
        rows[puzzle_id] = dict(row)
    return rows


def _aliases(row: Mapping[str, str]) -> list[dict[str, str]]:
    aliases: list[dict[str, str]] = []
    for field in ("game_puzzle_id", "leaderboard_key"):
        value = row.get(field)
        if value:
            aliases.append({"system": field, "value": value})
    return aliases


def _payload(
    artifact: Mapping[str, Any],
    *,
    payload_policy: str,
    store: ContentStore | None,
) -> str | None:
    if (
        payload_policy != "include-permitted"
        or artifact.get("rights_status") != "redistributable"
    ):
        return None
    if store is None:
        raise ReleaseMaterializationError(
            "include-permitted release materialization requires the authoritative ContentStore"
        )
    try:
        stored = store.require(artifact["sha256"], artifact["byte_length"])
        if stored.object_key != artifact.get("object_key"):
            artifact_id = artifact.get("artifact_id")
            raise ReleaseMaterializationError(
                f"{artifact_id}: content object key does not match canonical artifact"
            )
        payload = store.object_path(stored.sha256).read_bytes()
    except ContentStoreError as exc:
        raise ReleaseMaterializationError(str(exc)) from exc
    except OSError as exc:
        raise ReleaseMaterializationError(
            f"cannot read content object for {artifact.get('artifact_id')}"
        ) from exc
    return base64.b64encode(payload).decode("ascii")


def _observation_id(body: Mapping[str, Any]) -> str:
    digest = sha256_bytes(canonical_json_bytes(dict(body)))
    return f"om.observation.sha256.{digest}"


def _puzzle_observation(
    provenance: object,
    puzzle_by_artifact_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    row = _mapping(provenance, label="puzzle provenance")
    artifact_id = row.get("artifact_id")
    artifact = puzzle_by_artifact_id.get(artifact_id)
    if artifact is None:
        raise ReleaseMaterializationError(
            f"puzzle provenance references unknown artifact {artifact_id!r}"
        )
    if row.get("puzzle_id") != artifact.get("puzzle_id"):
        raise ReleaseMaterializationError(
            f"{artifact_id}: puzzle provenance references a different puzzle"
        )
    source_role = row.get("source_role")
    if source_role == "artifact":
        observation_role = "artifact"
    elif source_role == "evidence":
        observation_role = "metadata"
    else:
        raise ReleaseMaterializationError(
            f"{artifact_id}: unsupported puzzle provenance role {source_role!r}"
        )
    body = {
        "artifact_kind": "puzzle",
        "artifact_id": artifact_id,
        "puzzle_id": row["puzzle_id"],
        "source_role": observation_role,
        "source_id": row["source_id"],
        "source_revision": row.get("source_revision"),
        "source_object_id": row.get("source_object_id"),
        "source_path": row.get("source_path"),
        "associated_artifact_path": None,
        "source_declared_puzzle_id": row.get("source_object_id"),
        "source_url": row.get("source_url"),
        "author": row.get("author"),
        "retrieved_at": row["retrieved_at"],
        "claimed_cost": row.get("claimed_cost"),
        "claimed_cycles": row.get("claimed_cycles"),
        "claimed_area": row.get("claimed_area"),
        "claimed_instructions": row.get("claimed_instructions"),
        "observed_sha256": row.get("observed_sha256"),
        "source_evidence_sha256": row.get("source_evidence_sha256"),
        "source_evidence_byte_length": row.get("source_evidence_byte_length"),
        "rights_status": row["rights_status"],
        "importer_version": RELEASE_MATERIALIZER_VERSION,
    }
    return {"observation_id": _observation_id(body), **body}


def _validate_observation(
    row: Mapping[str, Any],
    *,
    collection_rows: Mapping[str, Mapping[str, Any]],
    puzzle_by_artifact_id: Mapping[str, Mapping[str, Any]],
    solution_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    validator = Draft202012Validator(
        load_schema("observations"),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(dict(row)),
        key=lambda error: (list(error.path), error.message),
    )
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise ReleaseMaterializationError(
            f"observation violates the release schema: {detail}"
        )

    body = dict(row)
    supplied_id = body.pop("observation_id")
    if supplied_id != _observation_id(body):
        raise ReleaseMaterializationError(
            "observation identity does not match canonical observation body"
        )

    artifact_id = row.get("artifact_id")
    puzzle_id = row.get("puzzle_id")
    if artifact_id is None:
        if puzzle_id is not None and puzzle_id not in collection_rows:
            raise ReleaseMaterializationError(
                f"metadata observation references puzzle outside collection: {puzzle_id!r}"
            )
        return

    artifact_kind = row.get("artifact_kind")
    if artifact_kind == "puzzle":
        artifact = puzzle_by_artifact_id.get(artifact_id)
    else:
        artifact = solution_by_id.get(artifact_id)
    if artifact is None:
        raise ReleaseMaterializationError(
            f"observation references unknown {artifact_kind} artifact {artifact_id!r}"
        )
    if puzzle_id != artifact.get("puzzle_id"):
        raise ReleaseMaterializationError(
            f"{artifact_id}: observation puzzle does not match canonical artifact"
        )
    if row.get("observed_sha256") != artifact.get("sha256"):
        raise ReleaseMaterializationError(
            f"{artifact_id}: observation sha256 does not match canonical artifact"
        )


def _validated_rows(
    config_name: str,
    rows: list[dict[str, Any]],
    *,
    payload_policy: str,
) -> list[dict[str, Any]]:
    validator = Draft202012Validator(
        load_schema(config_name),
        format_checker=FormatChecker(),
    )
    for index, row in enumerate(rows, start=1):
        errors = sorted(
            validator.iter_errors(row),
            key=lambda error: (list(error.path), error.message),
        )
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise ReleaseMaterializationError(
                f"{config_name} row {index} violates the release schema: {detail}"
            )
    validate_payload_policy(config_name, rows, payload_policy)
    return sort_records(config_name, rows)


def materialize_release_records(
    collection: CollectionDefinition,
    *,
    puzzle_artifacts: Iterable[object],
    solution_artifacts: Iterable[object],
    observations: Iterable[object],
    verifications: Iterable[object],
    normalized_solutions: Iterable[object],
    puzzle_provenance: Iterable[object] = (),
    payload_policy: str = "metadata-only",
    store: ContentStore | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Project canonical entities into the existing four release configs."""

    collection_rows = _collection_rows(collection)
    puzzle_by_id: dict[str, dict[str, Any]] = {}
    puzzle_by_artifact_id: dict[str, dict[str, Any]] = {}
    for value in puzzle_artifacts:
        artifact = _mapping(value, label="puzzle artifact")
        _validate_artifact(artifact, kind="puzzle")
        puzzle_id = artifact.get("puzzle_id")
        if puzzle_id not in collection_rows:
            raise ReleaseMaterializationError(
                f"puzzle artifact references puzzle outside collection: {puzzle_id!r}"
            )
        if puzzle_id in puzzle_by_id:
            raise ReleaseMaterializationError(
                f"{puzzle_id}: multiple canonical puzzle artifacts cannot be projected"
            )
        artifact_id = artifact["artifact_id"]
        if artifact_id in puzzle_by_artifact_id:
            raise ReleaseMaterializationError(
                f"{artifact_id}: puzzle artifact identity is associated with multiple puzzles"
            )
        puzzle_by_id[puzzle_id] = artifact
        puzzle_by_artifact_id[artifact_id] = artifact

    solution_by_id = _unique_by(
        solution_artifacts,
        "artifact_id",
        label="solution artifact",
    )
    for artifact in solution_by_id.values():
        _validate_artifact(artifact, kind="solution")
        puzzle_id = artifact.get("puzzle_id")
        if puzzle_id not in collection_rows:
            raise ReleaseMaterializationError(
                f"solution artifact references puzzle outside collection: {puzzle_id!r}"
            )
        if puzzle_id not in puzzle_by_id:
            raise ReleaseMaterializationError(
                f"{artifact['artifact_id']}: missing canonical puzzle artifact "
                f"for {puzzle_id}"
            )

    verification_by_solution = _unique_by(
        verifications,
        "solution_id",
        label="verification",
    )
    for verification in verification_by_solution.values():
        _validate_verification(verification)

    normalized_by_solution = _unique_by(
        normalized_solutions,
        "solution_id",
        label="normalized solution",
    )
    for normalized in normalized_by_solution.values():
        _validate_normalized_identity(normalized)

    observation_rows = [_mapping(value, label="observation") for value in observations]
    observation_rows.extend(
        _puzzle_observation(value, puzzle_by_artifact_id) for value in puzzle_provenance
    )
    observation_by_id = _unique_by(
        observation_rows,
        "observation_id",
        label="observation",
    )
    observation_rows = list(observation_by_id.values())

    observed_artifact_ids: set[str] = set()
    source_ids_by_solution: dict[str, set[str]] = {}
    for observation in observation_rows:
        _validate_observation(
            observation,
            collection_rows=collection_rows,
            puzzle_by_artifact_id=puzzle_by_artifact_id,
            solution_by_id=solution_by_id,
        )
        artifact_id = observation.get("artifact_id")
        source_id = observation.get("source_id")
        if isinstance(artifact_id, str):
            observed_artifact_ids.add(artifact_id)
        if artifact_id in solution_by_id and isinstance(source_id, str) and source_id:
            source_ids_by_solution.setdefault(artifact_id, set()).add(source_id)

    for artifact_id in sorted(puzzle_by_artifact_id):
        if artifact_id not in observed_artifact_ids:
            raise ReleaseMaterializationError(
                f"{artifact_id}: puzzle artifact has no provenance observation"
            )

    puzzle_rows: list[dict[str, Any]] = []
    for puzzle_id, artifact in puzzle_by_id.items():
        inventory = collection_rows[puzzle_id]
        puzzle_rows.append(
            {
                "puzzle_id": puzzle_id,
                "display_name": inventory["display_name"],
                "kind": inventory["kind"],
                "aliases": _aliases(inventory),
                "canonical_puzzle_artifact_id": artifact["artifact_id"],
                "puzzle_sha256": artifact["sha256"],
                "puzzle_bytes": _payload(
                    artifact,
                    payload_policy=payload_policy,
                    store=store,
                ),
                "rights_status": artifact["rights_status"],
                "collection_id": collection.collection_id,
            }
        )

    solution_rows: list[dict[str, Any]] = []
    for solution_id, artifact in solution_by_id.items():
        verification = verification_by_solution.get(solution_id)
        if verification is None:
            raise ReleaseMaterializationError(
                f"{solution_id}: missing canonical Verification record"
            )
        puzzle_id = artifact["puzzle_id"]
        puzzle_artifact = puzzle_by_id[puzzle_id]
        if verification.get("puzzle_artifact_id") != puzzle_artifact["artifact_id"]:
            raise ReleaseMaterializationError(
                f"{solution_id}: Verification puzzle artifact does not match "
                "canonical puzzle artifact"
            )

        normalized = normalized_by_solution.get(solution_id)
        if normalized is not None and normalized.get("puzzle_id") != puzzle_id:
            raise ReleaseMaterializationError(
                f"{solution_id}: normalized solution references a different puzzle"
            )
        sources = source_ids_by_solution.get(solution_id, set())
        if not sources:
            raise ReleaseMaterializationError(
                f"{solution_id}: no source observation preserves artifact provenance"
            )

        verified = (
            verification.get("parse_status") == "passed"
            and verification.get("simulation_status") == "passed"
        )
        solution_rows.append(
            {
                "solution_id": solution_id,
                "solution_sha256": artifact["sha256"],
                "puzzle_id": puzzle_id,
                "puzzle_artifact_id": puzzle_artifact["artifact_id"],
                "solution_format": artifact["artifact_format"],
                "solution_bytes": _payload(
                    artifact,
                    payload_policy=payload_policy,
                    store=store,
                ),
                "rights_status": artifact["rights_status"],
                "verified": verified,
                "validation_profile": verification["validation_profile"],
                "verifier_revision": verification["verifier_revision"],
                "cost": verification.get("cost"),
                "cycles": verification.get("cycles"),
                "area": verification.get("area"),
                "instructions": verification.get("instructions"),
                "vanilla_constructible": verification.get("vanilla_constructible"),
                "record_eligible": verification.get("record_eligible"),
                "normalized_solution_id": (
                    normalized.get("normalized_solution_id")
                    if normalized is not None
                    else None
                ),
                "source_count": len(sources),
                "collection_id": collection.collection_id,
            }
        )

    extra_verifications = set(verification_by_solution) - set(solution_by_id)
    if extra_verifications:
        raise ReleaseMaterializationError(
            "Verification references unknown solution(s): "
            + ", ".join(sorted(extra_verifications))
        )
    extra_normalized = set(normalized_by_solution) - set(solution_by_id)
    if extra_normalized:
        raise ReleaseMaterializationError(
            "normalized record references unknown solution(s): "
            + ", ".join(sorted(extra_normalized))
        )

    records = {
        "puzzles": _validated_rows(
            "puzzles",
            puzzle_rows,
            payload_policy=payload_policy,
        ),
        "solutions": _validated_rows(
            "solutions",
            solution_rows,
            payload_policy=payload_policy,
        ),
        "observations": _validated_rows(
            "observations",
            observation_rows,
            payload_policy=payload_policy,
        ),
        "normalized": _validated_rows(
            "normalized",
            list(normalized_by_solution.values()),
            payload_policy=payload_policy,
        ),
    }
    return records


def _release_metadata_template(output_dir: Path) -> dict[str, Any]:
    path = Path(output_dir) / "release-metadata.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseMaterializationError(
            f"release metadata template is missing or invalid: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ReleaseMaterializationError("release metadata template must be an object")
    schema_version = value.get("corpus_schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        raise ReleaseMaterializationError(
            "release metadata template requires corpus_schema_version"
        )
    supplied = sorted(_DERIVED_RELEASE_METADATA_FIELDS & set(value))
    if supplied:
        raise ReleaseMaterializationError(
            "derived release metadata must not be hand-authored: " + ", ".join(supplied)
        )
    return value


def _derived_release_metadata(
    template: Mapping[str, Any],
    *,
    verifications: Iterable[object],
    normalized_rows: Iterable[Mapping[str, Any]],
    observation_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    verification_rows = [_mapping(value, label="verification") for value in verifications]
    verifier_identities = {
        (
            row["verifier_implementation"],
            row["verifier_revision"],
            row["verifier_sha256"],
            row["validation_profile"],
        )
        for row in verification_rows
    }
    if len(verifier_identities) > 1:
        raise ReleaseMaterializationError(
            "release contains multiple verifier identities; one manifest identity is required"
        )
    verifier_identity = next(iter(verifier_identities), None)

    normalizer_versions = {row["normalizer_version"] for row in normalized_rows}
    if len(normalizer_versions) > 1:
        raise ReleaseMaterializationError(
            "release contains multiple normalizer versions; one manifest version is required"
        )
    normalizer_version = next(iter(normalizer_versions), None)

    source_classes = sorted(
        {
            (row["source_id"], row.get("source_revision"))
            for row in observation_rows
        },
        key=lambda value: (value[0], value[1] or ""),
    )

    result = dict(template)
    result.update(
        {
            "verifier_revision": verifier_identity[1] if verifier_identity else None,
            "verifier_sha256": verifier_identity[2] if verifier_identity else None,
            "validation_profile": verifier_identity[3] if verifier_identity else None,
            "normalizer_version": normalizer_version,
            "source_classes": [
                {"source_id": source_id, "revision": revision}
                for source_id, revision in source_classes
            ],
        }
    )
    return result


def materialize_release_inputs(
    collection: CollectionDefinition,
    output_dir: Path,
    *,
    puzzle_artifacts: Iterable[object],
    solution_artifacts: Iterable[object],
    observations: Iterable[object],
    verifications: Iterable[object],
    normalized_solutions: Iterable[object],
    puzzle_provenance: Iterable[object] = (),
    payload_policy: str = "metadata-only",
    store: ContentStore | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Project canonical entities and bind the existing release input metadata."""

    puzzle_artifacts = tuple(puzzle_artifacts)
    puzzle_provenance = tuple(puzzle_provenance)
    solution_artifacts = tuple(solution_artifacts)
    observations = tuple(observations)
    verifications = tuple(verifications)
    normalized_solutions = tuple(normalized_solutions)

    template = _release_metadata_template(output_dir)
    records = materialize_release_records(
        collection,
        puzzle_artifacts=puzzle_artifacts,
        puzzle_provenance=puzzle_provenance,
        solution_artifacts=solution_artifacts,
        observations=observations,
        verifications=verifications,
        normalized_solutions=normalized_solutions,
        payload_policy=payload_policy,
        store=store,
    )
    metadata = _derived_release_metadata(
        template,
        verifications=verifications,
        normalized_rows=records["normalized"],
        observation_rows=records["observations"],
    )
    write_release_inputs(records, output_dir)
    (Path(output_dir) / "release-metadata.json").write_bytes(
        canonical_json_bytes(metadata) + b"\n"
    )
    return records


def write_release_inputs(
    records: Mapping[str, Iterable[Mapping[str, Any]]],
    output_dir: Path,
) -> Path:
    """Write the four release inputs in canonical config and row order."""

    if set(records) != set(CONFIG_NAMES):
        missing = sorted(set(CONFIG_NAMES) - set(records))
        extra = sorted(set(records) - set(CONFIG_NAMES))
        detail: list[str] = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        raise ReleaseMaterializationError(
            "invalid release config set: " + "; ".join(detail)
        )

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for config_name in CONFIG_NAMES:
        rows = sort_records(config_name, [dict(row) for row in records[config_name]])
        payload = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        (destination / f"{config_name}.jsonl").write_bytes(payload)
    return destination
