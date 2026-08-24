from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .cache import CacheReceipt, ContentAddressedCache
from .content_store import ContentStore
from .errors import CorpusError
from .ingestion import (
    ArtifactProvenance,
    ArtifactRecord,
    ObservedArtifactCandidate,
    ingest_artifacts,
)
from .solution_sources import (
    OM_ARCHIVE_SOURCE,
    OM_LEADERBOARD_SOURCE,
    CollectionInventory,
    SolutionSourceLayout,
)

_IMPORTER_VERSION = "solution-materializer-v1"


class SolutionMaterializationError(CorpusError):
    """Raised when cached solution facts cannot be mapped unambiguously."""


@dataclass(frozen=True)
class Observation:
    observation_id: str
    artifact_kind: str
    artifact_id: str | None
    puzzle_id: str
    source_role: str
    source_id: str
    source_revision: str
    source_object_id: str | None
    source_path: str
    associated_artifact_path: str | None
    source_declared_puzzle_id: str | None
    source_url: str | None
    author: str | None
    retrieved_at: str
    claimed_cost: int | None
    claimed_cycles: int | None
    claimed_area: int | None
    claimed_instructions: int | None
    observed_sha256: str | None
    source_evidence_sha256: str
    source_evidence_byte_length: int
    rights_status: str
    importer_version: str


@dataclass(frozen=True)
class SolutionMaterializationResult:
    artifacts: tuple[ArtifactRecord, ...]
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class _MetadataContext:
    associated_artifact_path: str | None
    source_declared_puzzle_id: str | None


def _load_receipts(root: Path, source: SolutionSourceLayout) -> tuple[CacheReceipt, ...]:
    cache = ContentAddressedCache(root)
    receipt_root = root / "receipts" / source.source_id / source.pinned_revision
    if not receipt_root.exists():
        return ()
    receipts: list[CacheReceipt] = []
    for path in sorted(receipt_root.rglob("*.json")):
        receipt = cache._read_receipt(path)
        if receipt.source_id != source.source_id or receipt.revision != source.pinned_revision:
            raise SolutionMaterializationError(
                f"receipt identity mismatch under {source.source_id}@{source.pinned_revision}: "
                f"{receipt.upstream_path}"
            )
        receipts.append(receipt)
    return tuple(receipts)


def _mapped_receipts(
    receipts: tuple[CacheReceipt, ...], directories: dict[str, str], suffix: str
) -> dict[str, tuple[str, CacheReceipt]]:
    mapped: dict[str, tuple[str, CacheReceipt]] = {}
    for receipt in receipts:
        path = PurePosixPath(receipt.upstream_path)
        puzzle_id = directories.get(path.parent.as_posix())
        if puzzle_id is None or path.suffix != suffix:
            continue
        previous = mapped.setdefault(receipt.upstream_path, (puzzle_id, receipt))
        if previous != (puzzle_id, receipt):
            raise SolutionMaterializationError(
                f"conflicting receipt facts for {receipt.source_id}:{receipt.upstream_path}"
            )
    return mapped


def _read_json_evidence(store: ContentStore, receipt: CacheReceipt) -> dict[str, Any]:
    store.require(receipt.sha256, receipt.byte_length)
    try:
        value = json.loads(store.object_path(receipt.sha256).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SolutionMaterializationError(
            f"invalid leaderboard metadata {receipt.upstream_path}"
        ) from exc
    if not isinstance(value, dict):
        raise SolutionMaterializationError(
            f"leaderboard metadata must be an object: {receipt.upstream_path}"
        )
    return value


def _metric(score: dict[str, Any], name: str, source_path: str) -> int | None:
    value = score.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SolutionMaterializationError(f"invalid {name} claim in {source_path}")
    return value


def _metadata_claims(
    data: dict[str, Any], source_path: str
) -> tuple[int | None, int | None, int | None, int | None]:
    score = data.get("score")
    if score is None:
        score = {}
    if not isinstance(score, dict):
        raise SolutionMaterializationError(f"invalid score object in {source_path}")
    return (
        _metric(score, "cost", source_path),
        _metric(score, "cycles", source_path),
        _metric(score, "area", source_path),
        _metric(score, "instructions", source_path),
    )


def _source_url(data: dict[str, Any], source_path: str) -> str | None:
    for field in ("dataLink", "displayLink"):
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise SolutionMaterializationError(f"invalid {field} in {source_path}")
        return value
    return None


def _source_declared_puzzle_id(data: dict[str, Any], source_path: str) -> str | None:
    value = data.get("puzzle")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise SolutionMaterializationError(f"invalid puzzle identifier in {source_path}")
    return value


def _data_path(data: dict[str, Any], source_path: str) -> str | None:
    value = data.get("dataPath")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise SolutionMaterializationError(f"invalid dataPath in {source_path}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".solution":
        raise SolutionMaterializationError(f"invalid dataPath in {source_path}: {value!r}")
    return path.as_posix()


def _resolve_data_path(
    metadata_path: str,
    data_path: str | None,
    solutions: dict[str, tuple[str, CacheReceipt]],
    directories: dict[str, str],
    puzzle_id: str,
) -> tuple[str | None, CacheReceipt | None]:
    if data_path is None:
        return None, None
    metadata_parent = PurePosixPath(metadata_path).parent
    declared_path = PurePosixPath(data_path)
    declared_parent = declared_path.parent.as_posix()
    declared_puzzle_id = directories.get(declared_parent)
    if declared_puzzle_id is not None and declared_puzzle_id != puzzle_id:
        raise SolutionMaterializationError(
            f"metadata {metadata_path} dataPath points to a different puzzle"
        )

    source_relative_path = (metadata_parent / declared_path).as_posix()
    candidates = {declared_path.as_posix(), source_relative_path}
    matches = [(path, solutions[path]) for path in sorted(candidates) if path in solutions]
    if len(matches) > 1:
        raise SolutionMaterializationError(f"ambiguous dataPath in {metadata_path}: {data_path!r}")
    if not matches:
        if declared_puzzle_id is not None:
            return declared_path.as_posix(), None
        return source_relative_path, None

    resolved_path, (target_puzzle_id, receipt) = matches[0]
    if target_puzzle_id != puzzle_id:
        raise SolutionMaterializationError(
            f"metadata {metadata_path} dataPath points to a different puzzle"
        )
    return resolved_path, receipt


def _observation_id(values: dict[str, Any]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return f"om.observation.sha256.{hashlib.sha256(payload).hexdigest()}"


def _make_observation(**values: Any) -> Observation:
    body = dict(values)
    return Observation(observation_id=_observation_id(body), **body)


def _observation_from_provenance(
    row: ArtifactProvenance,
    metadata_contexts: dict[str, _MetadataContext],
) -> Observation:
    is_metadata = row.source_role == "evidence"
    context = metadata_contexts.get(row.source_path) if is_metadata else None
    if is_metadata and context is None:
        raise SolutionMaterializationError(
            f"missing metadata context for evidence observation {row.source_path}"
        )
    return _make_observation(
        artifact_kind="solution",
        artifact_id=row.artifact_id,
        puzzle_id=row.puzzle_id,
        source_role="metadata" if is_metadata else "artifact",
        source_id=row.source_id,
        source_revision=row.source_revision,
        source_object_id=row.source_object_id,
        source_path=row.source_path,
        associated_artifact_path=context.associated_artifact_path if context else None,
        source_declared_puzzle_id=context.source_declared_puzzle_id if context else None,
        source_url=row.source_url,
        author=row.author,
        retrieved_at=row.retrieved_at,
        claimed_cost=row.claimed_cost,
        claimed_cycles=row.claimed_cycles,
        claimed_area=row.claimed_area,
        claimed_instructions=row.claimed_instructions,
        observed_sha256=row.observed_sha256,
        source_evidence_sha256=row.source_evidence_sha256,
        source_evidence_byte_length=row.source_evidence_byte_length,
        rights_status=row.rights_status,
        importer_version=_IMPORTER_VERSION,
    )


def _unpaired_metadata_observation(
    puzzle_id: str,
    receipt: CacheReceipt,
    data: dict[str, Any],
    context: _MetadataContext,
) -> Observation:
    claimed_cost, claimed_cycles, claimed_area, claimed_instructions = _metadata_claims(
        data, receipt.upstream_path
    )
    return _make_observation(
        artifact_kind="solution",
        artifact_id=None,
        puzzle_id=puzzle_id,
        source_role="metadata",
        source_id=receipt.source_id,
        source_revision=receipt.revision,
        source_object_id=None,
        source_path=receipt.upstream_path,
        associated_artifact_path=context.associated_artifact_path,
        source_declared_puzzle_id=context.source_declared_puzzle_id,
        source_url=_source_url(data, receipt.upstream_path),
        author=None,
        retrieved_at=receipt.retrieved_at,
        claimed_cost=claimed_cost,
        claimed_cycles=claimed_cycles,
        claimed_area=claimed_area,
        claimed_instructions=claimed_instructions,
        observed_sha256=None,
        source_evidence_sha256=receipt.sha256,
        source_evidence_byte_length=receipt.byte_length,
        rights_status=receipt.rights_status,
        importer_version=_IMPORTER_VERSION,
    )


def _observation_sort_key(row: Observation) -> tuple[str, ...]:
    return (
        row.puzzle_id,
        row.artifact_id or "",
        row.source_id,
        row.source_revision,
        row.source_path,
        row.source_role,
        row.associated_artifact_path or "",
        row.source_declared_puzzle_id or "",
        row.source_object_id or "",
        row.observation_id,
    )


def materialize_solution_facts(
    collection: CollectionInventory,
    cache_root: Path,
) -> SolutionMaterializationResult:
    root = Path(cache_root)
    store = ContentStore(root)
    archive_receipts = _load_receipts(root, OM_ARCHIVE_SOURCE)
    leaderboard_receipts = _load_receipts(root, OM_LEADERBOARD_SOURCE)

    archive_solutions = _mapped_receipts(
        archive_receipts,
        OM_ARCHIVE_SOURCE.expected_directories(collection),
        ".solution",
    )
    leaderboard_directories = OM_LEADERBOARD_SOURCE.expected_directories(collection)
    leaderboard_solutions = _mapped_receipts(
        leaderboard_receipts,
        leaderboard_directories,
        ".solution",
    )
    leaderboard_metadata = _mapped_receipts(
        leaderboard_receipts,
        leaderboard_directories,
        ".json",
    )

    candidates = [
        ObservedArtifactCandidate("solution", puzzle_id, "solution", receipt)
        for puzzle_id, receipt in archive_solutions.values()
    ]
    candidates.extend(
        ObservedArtifactCandidate("solution", puzzle_id, "solution", receipt)
        for puzzle_id, receipt in leaderboard_solutions.values()
    )

    metadata_contexts: dict[str, _MetadataContext] = {}
    unpaired: list[Observation] = []
    for metadata_path, (puzzle_id, metadata_receipt) in sorted(leaderboard_metadata.items()):
        data = _read_json_evidence(store, metadata_receipt)
        data_path = _data_path(data, metadata_receipt.upstream_path)
        resolved_path, solution_receipt = _resolve_data_path(
            metadata_receipt.upstream_path,
            data_path,
            leaderboard_solutions,
            leaderboard_directories,
            puzzle_id,
        )
        context = _MetadataContext(
            associated_artifact_path=resolved_path,
            source_declared_puzzle_id=_source_declared_puzzle_id(
                data,
                metadata_receipt.upstream_path,
            ),
        )
        metadata_contexts[metadata_path] = context
        if solution_receipt is None:
            unpaired.append(
                _unpaired_metadata_observation(
                    puzzle_id,
                    metadata_receipt,
                    data,
                    context,
                )
            )
            continue

        claimed_cost, claimed_cycles, claimed_area, claimed_instructions = _metadata_claims(
            data, metadata_receipt.upstream_path
        )
        candidates.append(
            ObservedArtifactCandidate(
                artifact_kind="solution",
                puzzle_id=puzzle_id,
                artifact_format="solution",
                artifact_receipt=solution_receipt,
                evidence_receipt=metadata_receipt,
                source_object_id=None,
                source_url=_source_url(data, metadata_receipt.upstream_path),
                author=None,
                claimed_cost=claimed_cost,
                claimed_cycles=claimed_cycles,
                claimed_area=claimed_area,
                claimed_instructions=claimed_instructions,
            )
        )

    ingested = ingest_artifacts(candidates, store)
    observations = [
        _observation_from_provenance(row, metadata_contexts) for row in ingested.provenance
    ]
    observations.extend(unpaired)
    return SolutionMaterializationResult(
        artifacts=ingested.artifacts,
        observations=tuple(sorted(set(observations), key=_observation_sort_key)),
    )
