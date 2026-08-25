from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .adapters.official_game import (
    OfficialGameAcquisitionError,
    OfficialGameAdapter,
    parse_official_manifest,
)
from .adapters.omsim import OmsimAdapter
from .cache import CacheReceipt, ContentAddressedCache
from .collections import CollectionDefinition
from .content_store import ContentStore
from .errors import CorpusError
from .hashing import sha256_bytes
from .ingestion import (
    ArtifactProvenance,
    ArtifactRecord,
    ObservedArtifactCandidate,
    ingest_artifacts,
)
from .observations import observation_id
from .puzzle_decoder import decode_puzzle_definition_evidence
from .puzzle_definition import PuzzleDefinitionEvidence, validate_puzzle_definition
from .puzzle_parser import parse_puzzle_bytes


class PuzzleMaterializationError(CorpusError):
    """Raised when cached puzzle facts cannot be mapped unambiguously."""


class PuzzleCoverageError(PuzzleMaterializationError):
    """Raised when required puzzles are not ready for exact-byte verification."""


@dataclass(frozen=True)
class PuzzleCoverage:
    puzzle_id: str
    puzzle_definition_id: str | None
    artifact_ids: tuple[str, ...]
    semantic_source_ids: tuple[str, ...]
    exact_source_ids: tuple[str, ...]
    semantic_covered: bool
    artifact_covered: bool
    verifier_ready: bool


@dataclass(frozen=True)
class PuzzleMaterializationResult:
    artifacts: tuple[ArtifactRecord, ...]
    provenance: tuple[ArtifactProvenance, ...]
    coverage: tuple[PuzzleCoverage, ...]


def _load_receipts(root: Path, source_id: str, revision: str) -> tuple[CacheReceipt, ...]:
    return tuple(ContentAddressedCache(root).iter_receipts(source_id, revision))


def _source_revisions(root: Path, source_id: str) -> tuple[str, ...]:
    source_root = root / "receipts" / source_id
    if not source_root.exists():
        return ()
    return tuple(sorted(path.name for path in source_root.iterdir() if path.is_dir()))


def _omsim_candidates(
    collection: CollectionDefinition,
    root: Path,
) -> tuple[ObservedArtifactCandidate, ...]:
    expected = {
        row["game_puzzle_id"]: row["puzzle_id"]
        for row in collection.inventory_rows
        if row["kind"] == "campaign"
    }
    seen: dict[str, str] = {}
    candidates: list[ObservedArtifactCandidate] = []
    for receipt in _load_receipts(root, OmsimAdapter.source_id, OmsimAdapter.pinned_revision):
        path = PurePosixPath(receipt.upstream_path)
        if path.parts[:3] != ("test", "puzzle", "campaign") or path.suffix != ".puzzle":
            continue
        game_puzzle_id = path.stem
        puzzle_id = expected.get(game_puzzle_id)
        if puzzle_id is None:
            continue
        previous = seen.setdefault(game_puzzle_id, receipt.upstream_path)
        if previous != receipt.upstream_path:
            raise PuzzleMaterializationError(
                f"omsim has multiple cached fixtures for {game_puzzle_id}: "
                f"{previous}, {receipt.upstream_path}"
            )
        candidates.append(
            ObservedArtifactCandidate(
                artifact_kind="puzzle",
                puzzle_id=puzzle_id,
                artifact_format="puzzle",
                artifact_receipt=receipt,
            )
        )
    return tuple(candidates)


def _official_candidates_for_revision(
    collection: CollectionDefinition,
    root: Path,
    revision: str,
) -> tuple[ObservedArtifactCandidate, ...]:
    source_id = OfficialGameAdapter.source_id
    receipts = _load_receipts(root, source_id, revision)
    if not receipts:
        return ()
    by_path = {receipt.upstream_path: receipt for receipt in receipts}
    if len(by_path) != len(receipts):
        raise PuzzleMaterializationError(f"{source_id}@{revision}: duplicate cached source path")

    manifest_receipt = by_path.get("official-puzzles.toml")
    if manifest_receipt is None:
        raise PuzzleMaterializationError(f"{source_id}@{revision}: missing cached manifest")
    store = ContentStore(root)
    store.require(manifest_receipt.sha256, manifest_receipt.byte_length)
    try:
        manifest_bytes = store.object_path(manifest_receipt.sha256).read_bytes()
    except OSError as exc:
        raise PuzzleMaterializationError(
            f"{source_id}@{revision}: cannot read cached manifest"
        ) from exc

    known_puzzles = {row["puzzle_id"] for row in collection.inventory_rows}
    try:
        manifest = parse_official_manifest(manifest_bytes, known_puzzles)
    except OfficialGameAcquisitionError as exc:
        raise PuzzleMaterializationError(
            f"{source_id}@{revision}: invalid cached manifest: {exc}"
        ) from exc

    expected_revision = f"local-{sha256_bytes(manifest.snapshot_id.encode('utf-8'))}"
    if revision != expected_revision:
        raise PuzzleMaterializationError(
            f"{source_id}@{revision}: snapshot identity does not match cache revision"
        )

    seen_paths: set[str] = set()
    candidates: list[ObservedArtifactCandidate] = []
    for mapping in manifest.mappings:
        puzzle_id = mapping.puzzle_id
        source_path = mapping.relative_path.as_posix()
        seen_paths.add(source_path)
        receipt = by_path.get(source_path)
        if receipt is None:
            raise PuzzleMaterializationError(
                f"{source_id}@{revision}: missing cached puzzle {source_path}"
            )
        candidates.append(
            ObservedArtifactCandidate(
                artifact_kind="puzzle",
                puzzle_id=puzzle_id,
                artifact_format="puzzle",
                artifact_receipt=receipt,
                evidence_receipt=manifest_receipt,
                source_object_id=puzzle_id,
            )
        )

    extra_puzzles = {
        path for path in by_path if path.endswith(".puzzle") and path not in seen_paths
    }
    if extra_puzzles:
        raise PuzzleMaterializationError(
            f"{source_id}@{revision}: cached puzzle is absent from manifest: "
            f"{', '.join(sorted(extra_puzzles))}"
        )
    return tuple(candidates)


def _official_candidates(
    collection: CollectionDefinition,
    root: Path,
) -> tuple[ObservedArtifactCandidate, ...]:
    candidates: list[ObservedArtifactCandidate] = []
    for revision in _source_revisions(root, OfficialGameAdapter.source_id):
        candidates.extend(_official_candidates_for_revision(collection, root, revision))
    return tuple(candidates)


def derive_puzzle_coverage(
    collection: CollectionDefinition,
    artifacts: Iterable[ArtifactRecord],
    provenance: Iterable[ArtifactProvenance],
    *,
    definitions: Iterable[Mapping[str, Any]] = (),
    semantic_source_ids_by_puzzle: Mapping[str, Iterable[str]] | None = None,
) -> tuple[PuzzleCoverage, ...]:
    artifact_ids: dict[str, set[str]] = {}
    exact_sources: dict[str, set[str]] = {}
    for artifact in artifacts:
        artifact_ids.setdefault(artifact.puzzle_id, set()).add(artifact.artifact_id)
    for row in provenance:
        if row.source_role == "artifact":
            exact_sources.setdefault(row.puzzle_id, set()).add(row.source_id)

    definition_by_puzzle: dict[str, Mapping[str, Any]] = {}
    for definition in definitions:
        validate_puzzle_definition(definition)
        puzzle_id = definition["puzzle_id"]
        if puzzle_id in definition_by_puzzle:
            raise PuzzleMaterializationError(
                f"{puzzle_id}: multiple semantic PuzzleDefinitions in coverage input"
            )
        definition_by_puzzle[puzzle_id] = definition

    source_map = semantic_source_ids_by_puzzle or {}
    rows: list[PuzzleCoverage] = []
    for puzzle in collection.inventory_rows:
        puzzle_id = puzzle["puzzle_id"]
        ids = tuple(sorted(artifact_ids.get(puzzle_id, ())))
        definition = definition_by_puzzle.get(puzzle_id)
        semantic_sources = tuple(sorted(set(source_map.get(puzzle_id, ()))))
        rows.append(
            PuzzleCoverage(
                puzzle_id=puzzle_id,
                puzzle_definition_id=(
                    str(definition["puzzle_definition_id"]) if definition is not None else None
                ),
                artifact_ids=ids,
                semantic_source_ids=semantic_sources,
                exact_source_ids=tuple(sorted(exact_sources.get(puzzle_id, ()))),
                semantic_covered=definition is not None,
                artifact_covered=bool(ids),
                verifier_ready=len(ids) == 1,
            )
        )
    return tuple(rows)


def materialize_puzzle_artifacts(
    collection: CollectionDefinition,
    cache_root: Path,
) -> PuzzleMaterializationResult:
    root = Path(cache_root)
    candidates = (*_omsim_candidates(collection, root), *_official_candidates(collection, root))
    ingested = ingest_artifacts(candidates, ContentStore(root))
    return PuzzleMaterializationResult(
        artifacts=ingested.artifacts,
        provenance=ingested.provenance,
        coverage=derive_puzzle_coverage(
            collection,
            ingested.artifacts,
            ingested.provenance,
        ),
    )


def _observation_mapping(value: object) -> dict[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise PuzzleMaterializationError("puzzle observation must be a mapping or dataclass")


def materialize_puzzle_provenance_observations(
    artifacts: Iterable[ArtifactRecord],
    provenance: Iterable[ArtifactProvenance],
) -> tuple[dict[str, Any], ...]:
    """Project exact puzzle provenance into canonical observation records."""

    by_artifact_id = {artifact.artifact_id: artifact for artifact in artifacts}
    rows: list[dict[str, Any]] = []
    for value in provenance:
        row = _observation_mapping(value)
        artifact_id = row.get("artifact_id")
        artifact = by_artifact_id.get(artifact_id)
        if artifact is None:
            raise PuzzleMaterializationError(
                f"puzzle provenance references unknown artifact {artifact_id!r}"
            )
        if row.get("puzzle_id") != artifact.puzzle_id:
            raise PuzzleMaterializationError(
                f"{artifact_id}: puzzle provenance references a different puzzle"
            )
        source_role = row.get("source_role")
        if source_role == "artifact":
            observation_role = "artifact"
        elif source_role == "evidence":
            observation_role = "metadata"
        else:
            raise PuzzleMaterializationError(
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
            "importer_version": "release-materializer-v1",
        }
        rows.append({"observation_id": observation_id(body), **body})
    return tuple(sorted(rows, key=lambda row: row["observation_id"]))


def materialize_puzzle_artifact_semantic_evidence(
    artifacts: Iterable[ArtifactRecord],
    observations: Iterable[object],
    store: ContentStore,
) -> tuple[PuzzleDefinitionEvidence, ...]:
    """Decode complete semantic evidence from canonical exact puzzle artifacts."""

    observation_rows = tuple(_observation_mapping(value) for value in observations)
    evidence: list[PuzzleDefinitionEvidence] = []
    seen_artifact_ids: set[str] = set()

    for artifact in sorted(artifacts, key=lambda row: (row.puzzle_id, row.artifact_id)):
        if artifact.artifact_id in seen_artifact_ids:
            raise PuzzleMaterializationError(
                f"duplicate puzzle artifact {artifact.artifact_id} in semantic materialization"
            )
        seen_artifact_ids.add(artifact.artifact_id)
        if artifact.artifact_kind != "puzzle" or artifact.artifact_format != "puzzle":
            raise PuzzleMaterializationError(
                f"cannot decode non-puzzle artifact {artifact.artifact_id}"
            )
        expected_id = f"om.puzzle-artifact.sha256.{artifact.sha256}"
        if artifact.artifact_id != expected_id:
            raise PuzzleMaterializationError(
                f"puzzle artifact identity does not match exact bytes: {artifact.artifact_id}"
            )

        stored = store.require(artifact.sha256, artifact.byte_length)
        if artifact.object_key != stored.object_key:
            raise PuzzleMaterializationError(
                f"puzzle artifact object key does not match content store: {artifact.artifact_id}"
            )

        matching_observations: list[str] = []
        for row in observation_rows:
            if row.get("artifact_id") != artifact.artifact_id:
                continue
            if row.get("source_role") != "artifact":
                continue
            if row.get("artifact_kind") != "puzzle":
                raise PuzzleMaterializationError(
                    f"{artifact.artifact_id}: observation has wrong artifact kind"
                )
            if row.get("puzzle_id") != artifact.puzzle_id:
                raise PuzzleMaterializationError(
                    f"{artifact.artifact_id}: observation references a different puzzle"
                )
            if row.get("observed_sha256") != artifact.sha256:
                raise PuzzleMaterializationError(
                    f"{artifact.artifact_id}: observation sha256 does not match exact artifact"
                )
            observation_value = row.get("observation_id")
            if not isinstance(observation_value, str) or not observation_value:
                raise PuzzleMaterializationError(
                    f"{artifact.artifact_id}: observation has invalid observation_id"
                )
            matching_observations.append(observation_value)

        if not matching_observations:
            raise PuzzleMaterializationError(
                f"{artifact.artifact_id}: no matching artifact observation"
            )

        try:
            payload = store.object_path(stored.sha256).read_bytes()
        except OSError as exc:
            raise PuzzleMaterializationError(
                f"cannot read puzzle artifact bytes: {artifact.artifact_id}"
            ) from exc
        parsed = parse_puzzle_bytes(payload)
        evidence.append(
            decode_puzzle_definition_evidence(
                parsed,
                puzzle_id=artifact.puzzle_id,
                observation_ids=tuple(sorted(set(matching_observations))),
                puzzle_artifact_id=artifact.artifact_id,
            )
        )

    return tuple(evidence)


def require_complete_puzzle_coverage(result: PuzzleMaterializationResult) -> None:
    missing = tuple(sorted(row.puzzle_id for row in result.coverage if not row.verifier_ready))
    if missing:
        raise PuzzleCoverageError(
            "missing unambiguous verifier-ready PuzzleArtifact coverage for: "
            + ", ".join(missing)
        )
