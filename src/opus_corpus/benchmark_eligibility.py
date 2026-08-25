from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .collections import CollectionDefinition
from .errors import CorpusError
from .hashing import canonical_json_bytes, sha256_bytes
from .ingestion import ArtifactProvenance, ArtifactRecord
from .puzzle_definition import validate_puzzle_definition

ELIGIBILITY_PROFILE = "exact-output-solve-v0.1"
ELIGIBILITY_VERSION = "1"

_PROTOCOL_PUZZLE_TYPES = frozenset({"normal", "polymer_height", "production"})
_SOURCE_PRIORITY = {"official-game": 0, "omsim": 1}
_OTHER_SOURCE_PRIORITY = 2


class BenchmarkEligibilityError(CorpusError):
    """Raised when canonical facts cannot produce unambiguous benchmark eligibility."""


@dataclass(frozen=True, slots=True)
class BenchmarkEligibilityEntry:
    puzzle_id: str
    puzzle_definition_id: str | None
    puzzle_type: str
    semantic_covered: bool
    artifact_covered: bool
    verifier_ready: bool
    eligible: bool
    exclusion_reason: str | None
    selected_puzzle_artifact_id: str | None
    selected_puzzle_artifact_sha256: str | None
    selected_puzzle_artifact_byte_length: int | None
    selected_puzzle_artifact_object_key: str | None
    selected_puzzle_artifact_rights_status: str | None
    selected_source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkEligibilityProjection:
    profile: str
    version: str
    collection_id: str
    collection_inventory_sha256: str
    entries: tuple[BenchmarkEligibilityEntry, ...]
    executable_entries: tuple[BenchmarkEligibilityEntry, ...]
    inventory_sha256: str
    inventory_id: str


def _collection_rows(collection: CollectionDefinition) -> tuple[Mapping[str, str], ...]:
    rows = tuple(collection.inventory_rows)
    seen: set[str] = set()
    for row in rows:
        puzzle_id = row.get("puzzle_id")
        if not isinstance(puzzle_id, str) or not puzzle_id:
            raise BenchmarkEligibilityError("collection contains an invalid puzzle_id")
        if puzzle_id in seen:
            raise BenchmarkEligibilityError(f"duplicate collection puzzle {puzzle_id}")
        seen.add(puzzle_id)
    return rows


def _definitions_by_puzzle(
    definitions: Iterable[Mapping[str, Any]],
    known_puzzles: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in definitions:
        record = dict(value)
        try:
            validate_puzzle_definition(record)
        except Exception as exc:
            raise BenchmarkEligibilityError(f"invalid puzzle definition: {exc}") from exc
        puzzle_id = record["puzzle_id"]
        if puzzle_id not in known_puzzles:
            raise BenchmarkEligibilityError(
                f"puzzle definition references puzzle outside collection: {puzzle_id}"
            )
        if puzzle_id in result:
            raise BenchmarkEligibilityError(f"duplicate puzzle definition for {puzzle_id}")
        result[puzzle_id] = record
    return result


def _artifacts_by_puzzle(
    artifacts: Iterable[ArtifactRecord],
    known_puzzles: set[str],
) -> tuple[dict[str, ArtifactRecord], dict[str, tuple[ArtifactRecord, ...]]]:
    by_id: dict[str, ArtifactRecord] = {}
    by_puzzle: dict[str, list[ArtifactRecord]] = {}
    for record in artifacts:
        if record.artifact_id in by_id:
            raise BenchmarkEligibilityError(f"duplicate puzzle artifact {record.artifact_id}")
        if record.artifact_kind != "puzzle":
            raise BenchmarkEligibilityError(
                f"benchmark eligibility accepts only puzzle artifacts: {record.artifact_id}"
            )
        if record.puzzle_id not in known_puzzles:
            raise BenchmarkEligibilityError(
                f"puzzle artifact references puzzle outside collection: {record.puzzle_id}"
            )
        expected_id = f"om.puzzle-artifact.sha256.{record.sha256}"
        if record.artifact_id != expected_id:
            raise BenchmarkEligibilityError(
                f"puzzle artifact identity does not match exact bytes: {record.artifact_id}"
            )
        by_id[record.artifact_id] = record
        by_puzzle.setdefault(record.puzzle_id, []).append(record)
    return by_id, {
        puzzle_id: tuple(sorted(records, key=lambda row: row.artifact_id))
        for puzzle_id, records in by_puzzle.items()
    }


def _artifact_sources(
    provenance: Iterable[ArtifactProvenance],
    artifacts_by_id: Mapping[str, ArtifactRecord],
) -> dict[str, tuple[str, ...]]:
    seen: set[tuple[object, ...]] = set()
    sources: dict[str, set[str]] = {}
    for row in provenance:
        identity = (
            row.artifact_id,
            row.source_role,
            row.source_id,
            row.source_revision,
            row.source_path,
            row.source_object_id,
        )
        if identity in seen:
            raise BenchmarkEligibilityError(
                f"duplicate puzzle artifact provenance for {row.artifact_id}"
            )
        seen.add(identity)
        artifact = artifacts_by_id.get(row.artifact_id)
        if artifact is None:
            raise BenchmarkEligibilityError(
                f"puzzle artifact provenance references unknown artifact {row.artifact_id}"
            )
        if row.puzzle_id != artifact.puzzle_id:
            raise BenchmarkEligibilityError(
                f"puzzle artifact provenance references wrong puzzle for {row.artifact_id}"
            )
        if row.observed_sha256 != artifact.sha256:
            raise BenchmarkEligibilityError(
                f"puzzle artifact provenance hash does not match {row.artifact_id}"
            )
        if row.source_role == "artifact":
            if not row.source_id:
                raise BenchmarkEligibilityError(
                    f"puzzle artifact provenance has empty source_id for {row.artifact_id}"
                )
            sources.setdefault(row.artifact_id, set()).add(row.source_id)
        elif row.source_role != "evidence":
            raise BenchmarkEligibilityError(
                f"unsupported puzzle artifact provenance role {row.source_role!r}"
            )
    return {
        artifact_id: tuple(sorted(source_ids))
        for artifact_id, source_ids in sources.items()
    }


def _selection_key(
    artifact: ArtifactRecord,
    source_ids: tuple[str, ...],
) -> tuple[int, str]:
    priority = min(
        (_SOURCE_PRIORITY.get(source_id, _OTHER_SOURCE_PRIORITY) for source_id in source_ids),
        default=_OTHER_SOURCE_PRIORITY,
    )
    return priority, artifact.artifact_id


def _select_verifier_artifact(
    artifacts: tuple[ArtifactRecord, ...],
    artifact_sources: Mapping[str, tuple[str, ...]],
) -> tuple[ArtifactRecord | None, tuple[str, ...]]:
    usable = [
        artifact
        for artifact in artifacts
        if artifact.artifact_format == "puzzle" and artifact_sources.get(artifact.artifact_id)
    ]
    if not usable:
        return None, ()
    selected = min(
        usable,
        key=lambda artifact: _selection_key(
            artifact,
            artifact_sources[artifact.artifact_id],
        ),
    )
    return selected, artifact_sources[selected.artifact_id]


def _inventory_payload(
    *,
    collection: CollectionDefinition,
    entries: tuple[BenchmarkEligibilityEntry, ...],
) -> dict[str, Any]:
    return {
        "profile": ELIGIBILITY_PROFILE,
        "version": ELIGIBILITY_VERSION,
        "collection_id": collection.collection_id,
        "collection_inventory_sha256": collection.inventory_sha256,
        "entries": [
            {
                "puzzle_id": entry.puzzle_id,
                "puzzle_definition_id": entry.puzzle_definition_id,
                "puzzle_type": entry.puzzle_type,
                "selected_puzzle_artifact_id": entry.selected_puzzle_artifact_id,
                "selected_puzzle_artifact_sha256": entry.selected_puzzle_artifact_sha256,
                "selected_puzzle_artifact_byte_length": entry.selected_puzzle_artifact_byte_length,
                "selected_puzzle_artifact_rights_status": (
                    entry.selected_puzzle_artifact_rights_status
                ),
                "selected_source_ids": list(entry.selected_source_ids),
            }
            for entry in entries
            if entry.eligible
        ],
    }


def derive_benchmark_eligibility(
    collection: CollectionDefinition,
    *,
    definitions: Iterable[Mapping[str, Any]],
    artifacts: Iterable[ArtifactRecord],
    provenance: Iterable[ArtifactProvenance],
) -> BenchmarkEligibilityProjection:
    """Derive exact-output Solve eligibility from canonical collection and puzzle facts."""

    collection_rows = _collection_rows(collection)
    known_puzzles = {row["puzzle_id"] for row in collection_rows}
    definitions_by_puzzle = _definitions_by_puzzle(definitions, known_puzzles)
    artifacts_by_id, artifacts_by_puzzle = _artifacts_by_puzzle(artifacts, known_puzzles)
    sources_by_artifact = _artifact_sources(provenance, artifacts_by_id)

    entries: list[BenchmarkEligibilityEntry] = []
    for row in collection_rows:
        puzzle_id = row["puzzle_id"]
        puzzle_type = row["puzzle_type"]
        definition = definitions_by_puzzle.get(puzzle_id)
        puzzle_artifacts = artifacts_by_puzzle.get(puzzle_id, ())
        selected, selected_sources = _select_verifier_artifact(
            puzzle_artifacts,
            sources_by_artifact,
        )
        semantic_covered = definition is not None
        artifact_covered = bool(puzzle_artifacts)
        verifier_ready = selected is not None
        protocol_compatible = puzzle_type in _PROTOCOL_PUZZLE_TYPES

        if not semantic_covered:
            exclusion_reason = "missing_semantic_definition"
        elif not artifact_covered:
            exclusion_reason = "missing_exact_artifact"
        elif not verifier_ready:
            exclusion_reason = "no_verifier_usable_artifact"
        elif not protocol_compatible:
            exclusion_reason = "protocol_incompatible"
        else:
            exclusion_reason = None

        entries.append(
            BenchmarkEligibilityEntry(
                puzzle_id=puzzle_id,
                puzzle_definition_id=(
                    str(definition["puzzle_definition_id"])
                    if definition is not None
                    else None
                ),
                puzzle_type=puzzle_type,
                semantic_covered=semantic_covered,
                artifact_covered=artifact_covered,
                verifier_ready=verifier_ready,
                eligible=exclusion_reason is None,
                exclusion_reason=exclusion_reason,
                selected_puzzle_artifact_id=(selected.artifact_id if selected else None),
                selected_puzzle_artifact_sha256=(selected.sha256 if selected else None),
                selected_puzzle_artifact_byte_length=(
                    selected.byte_length if selected else None
                ),
                selected_puzzle_artifact_object_key=(selected.object_key if selected else None),
                selected_puzzle_artifact_rights_status=(
                    selected.rights_status if selected else None
                ),
                selected_source_ids=selected_sources,
            )
        )

    entry_tuple = tuple(entries)
    executable_entries = tuple(entry for entry in entry_tuple if entry.eligible)
    inventory_payload = _inventory_payload(collection=collection, entries=entry_tuple)
    inventory_sha256 = sha256_bytes(canonical_json_bytes(inventory_payload))
    return BenchmarkEligibilityProjection(
        profile=ELIGIBILITY_PROFILE,
        version=ELIGIBILITY_VERSION,
        collection_id=collection.collection_id,
        collection_inventory_sha256=collection.inventory_sha256,
        entries=entry_tuple,
        executable_entries=executable_entries,
        inventory_sha256=inventory_sha256,
        inventory_id=f"om.benchmark-inventory.sha256.{inventory_sha256}",
    )


def benchmark_eligibility_bytes(result: BenchmarkEligibilityProjection) -> bytes:
    """Return one canonical byte representation of a derived eligibility projection."""

    return canonical_json_bytes(asdict(result))