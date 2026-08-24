from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .adapters.molecule_db import MoleculeDbAdapter
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


class PuzzleMaterializationError(CorpusError):
    """Raised when cached puzzle facts cannot be mapped unambiguously."""


class PuzzleCoverageError(PuzzleMaterializationError):
    """Raised when required puzzles lack verifier-usable exact artifacts."""


@dataclass(frozen=True)
class PuzzleCoverage:
    puzzle_id: str
    artifact_ids: tuple[str, ...]
    exact_source_ids: tuple[str, ...]
    semantic_source_ids: tuple[str, ...]
    verifier_usable: bool


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


def _molecule_db_semantic_puzzles(
    collection: CollectionDefinition,
    root: Path,
) -> frozenset[str]:
    adapter = MoleculeDbAdapter()
    receipts = _load_receipts(root, adapter.source_id, adapter.pinned_revision)
    if not receipts:
        return frozenset()
    by_path = {receipt.upstream_path: receipt for receipt in receipts}
    expected_paths = {"src/puzzle.rs", "src/molecules.rs"}
    if set(by_path) != expected_paths or len(by_path) != len(receipts):
        raise PuzzleMaterializationError(
            f"molecule-db@{adapter.pinned_revision}: incomplete or ambiguous semantic evidence"
        )

    store = ContentStore(root)
    payloads: dict[str, bytes] = {}
    for source_path in sorted(expected_paths):
        receipt = by_path[source_path]
        store.require(receipt.sha256, receipt.byte_length)
        try:
            payloads[source_path] = store.object_path(receipt.sha256).read_bytes()
        except OSError as exc:
            raise PuzzleMaterializationError(
                f"molecule-db@{adapter.pinned_revision}: cannot read {source_path}"
            ) from exc

    semantics = adapter.parse_collection_semantics(
        collection,
        puzzle_source=payloads["src/puzzle.rs"],
        molecules_source=payloads["src/molecules.rs"],
    )
    return frozenset(item.puzzle_id for item in semantics)


def _require_unambiguous_exact_artifacts(artifacts: tuple[ArtifactRecord, ...]) -> None:
    artifact_ids: dict[str, list[str]] = {}
    for artifact in artifacts:
        artifact_ids.setdefault(artifact.puzzle_id, []).append(artifact.artifact_id)

    for puzzle_id, ids in sorted(artifact_ids.items()):
        if len(ids) > 1:
            raise PuzzleMaterializationError(
                f"{puzzle_id}: multiple exact puzzle artifacts ({', '.join(sorted(ids))})"
            )


def _coverage(
    collection: CollectionDefinition,
    artifacts: tuple[ArtifactRecord, ...],
    provenance: tuple[ArtifactProvenance, ...],
    semantic_puzzle_ids: frozenset[str],
) -> tuple[PuzzleCoverage, ...]:
    artifact_ids: dict[str, set[str]] = {}
    exact_sources: dict[str, set[str]] = {}
    for artifact in artifacts:
        artifact_ids.setdefault(artifact.puzzle_id, set()).add(artifact.artifact_id)
    for row in provenance:
        if row.source_role == "artifact":
            exact_sources.setdefault(row.puzzle_id, set()).add(row.source_id)

    rows: list[PuzzleCoverage] = []
    for puzzle in collection.inventory_rows:
        puzzle_id = puzzle["puzzle_id"]
        ids = tuple(sorted(artifact_ids.get(puzzle_id, ())))
        semantic_sources = ("molecule-db",) if puzzle_id in semantic_puzzle_ids else ()
        rows.append(
            PuzzleCoverage(
                puzzle_id=puzzle_id,
                artifact_ids=ids,
                exact_source_ids=tuple(sorted(exact_sources.get(puzzle_id, ()))),
                semantic_source_ids=semantic_sources,
                verifier_usable=bool(ids),
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
    _require_unambiguous_exact_artifacts(ingested.artifacts)
    semantic_puzzle_ids = _molecule_db_semantic_puzzles(collection, root)
    return PuzzleMaterializationResult(
        artifacts=ingested.artifacts,
        provenance=ingested.provenance,
        coverage=_coverage(
            collection,
            ingested.artifacts,
            ingested.provenance,
            semantic_puzzle_ids,
        ),
    )


def require_complete_puzzle_coverage(result: PuzzleMaterializationResult) -> None:
    missing = tuple(sorted(row.puzzle_id for row in result.coverage if not row.verifier_usable))
    if missing:
        raise PuzzleCoverageError(
            "missing verifier-usable PuzzleArtifact coverage for: " + ", ".join(missing)
        )
