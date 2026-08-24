from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .cache import CacheReceipt
from .content_store import ContentStore, StoredObject
from .errors import CorpusError


class ArtifactIngestionError(CorpusError):
    """Raised when cached source evidence has an ambiguous artifact meaning."""


@dataclass(frozen=True)
class ObservedArtifactCandidate:
    artifact_kind: str
    puzzle_id: str
    artifact_format: str
    artifact_receipt: CacheReceipt
    evidence_receipt: CacheReceipt | None = None
    source_object_id: str | None = None
    source_url: str | None = None
    author: str | None = None
    claimed_cost: int | None = None
    claimed_cycles: int | None = None
    claimed_area: int | None = None
    claimed_instructions: int | None = None


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_kind: str
    artifact_id: str
    puzzle_id: str
    sha256: str
    byte_length: int
    artifact_format: str
    rights_status: str
    object_key: str


@dataclass(frozen=True)
class ArtifactProvenance:
    artifact_id: str
    puzzle_id: str
    source_role: str
    source_id: str
    source_revision: str
    source_path: str
    source_object_id: str | None
    source_url: str | None
    author: str | None
    retrieved_at: str
    rights_status: str
    observed_sha256: str
    source_evidence_sha256: str
    source_evidence_byte_length: int
    claimed_cost: int | None
    claimed_cycles: int | None
    claimed_area: int | None
    claimed_instructions: int | None


@dataclass(frozen=True)
class IngestionResult:
    artifacts: tuple[ArtifactRecord, ...]
    provenance: tuple[ArtifactProvenance, ...]


@dataclass(frozen=True)
class _IngestedCandidate:
    candidate: ObservedArtifactCandidate
    artifact: StoredObject
    evidence: StoredObject
    artifact_id: str


_RIGHTS_RANK = {"redistributable": 0, "unknown": 1, "local_fetch_only": 2}


def _artifact_id(kind: str, digest: str) -> str:
    if kind == "puzzle":
        return f"om.puzzle-artifact.sha256.{digest}"
    if kind == "solution":
        return f"om.solution.sha256.{digest}"
    raise ArtifactIngestionError(f"unsupported artifact kind {kind!r}")


def _receipt_identity(receipt: CacheReceipt) -> tuple[str, str, str]:
    return receipt.source_id, receipt.revision, receipt.upstream_path


def _validate_rights(status: str) -> None:
    if status not in _RIGHTS_RANK:
        raise ArtifactIngestionError(f"invalid rights status {status!r}")


def _validate_candidate(
    candidate: ObservedArtifactCandidate,
    store: ContentStore,
) -> _IngestedCandidate:
    _validate_rights(candidate.artifact_receipt.rights_status)
    artifact = store.require(
        candidate.artifact_receipt.sha256,
        candidate.artifact_receipt.byte_length,
    )
    evidence_receipt = candidate.evidence_receipt or candidate.artifact_receipt
    _validate_rights(evidence_receipt.rights_status)
    if (
        evidence_receipt.source_id != candidate.artifact_receipt.source_id
        or evidence_receipt.revision != candidate.artifact_receipt.revision
    ):
        raise ArtifactIngestionError(
            f"{candidate.puzzle_id}: attached evidence must share artifact source and revision"
        )
    if (
        _receipt_identity(evidence_receipt) == _receipt_identity(candidate.artifact_receipt)
        and evidence_receipt != candidate.artifact_receipt
    ):
        raise ArtifactIngestionError(
            f"{candidate.puzzle_id}: one receipt identity has conflicting receipt facts"
        )
    evidence = artifact
    if evidence_receipt != candidate.artifact_receipt:
        evidence = store.require(evidence_receipt.sha256, evidence_receipt.byte_length)
    return _IngestedCandidate(
        candidate=candidate,
        artifact=artifact,
        evidence=evidence,
        artifact_id=_artifact_id(candidate.artifact_kind, artifact.sha256),
    )


def _aggregate_rights(statuses: Iterable[str]) -> str:
    values = tuple(statuses)
    if not values:
        raise ArtifactIngestionError("empty artifact rights set")
    for status in values:
        _validate_rights(status)
    return max(values, key=_RIGHTS_RANK.__getitem__)


def _provenance_rows(item: _IngestedCandidate) -> tuple[ArtifactProvenance, ...]:
    candidate = item.candidate
    artifact_receipt = candidate.artifact_receipt
    evidence_receipt = candidate.evidence_receipt or artifact_receipt
    same_evidence = evidence_receipt == artifact_receipt
    artifact_row = ArtifactProvenance(
        item.artifact_id,
        candidate.puzzle_id,
        "artifact",
        artifact_receipt.source_id,
        artifact_receipt.revision,
        artifact_receipt.upstream_path,
        candidate.source_object_id if same_evidence else None,
        candidate.source_url if same_evidence else None,
        candidate.author if same_evidence else None,
        artifact_receipt.retrieved_at,
        artifact_receipt.rights_status,
        artifact_receipt.sha256,
        artifact_receipt.sha256,
        artifact_receipt.byte_length,
        candidate.claimed_cost if same_evidence else None,
        candidate.claimed_cycles if same_evidence else None,
        candidate.claimed_area if same_evidence else None,
        candidate.claimed_instructions if same_evidence else None,
    )
    if same_evidence:
        return (artifact_row,)
    evidence_row = ArtifactProvenance(
        item.artifact_id,
        candidate.puzzle_id,
        "evidence",
        evidence_receipt.source_id,
        evidence_receipt.revision,
        evidence_receipt.upstream_path,
        candidate.source_object_id,
        candidate.source_url,
        candidate.author,
        evidence_receipt.retrieved_at,
        evidence_receipt.rights_status,
        artifact_receipt.sha256,
        evidence_receipt.sha256,
        evidence_receipt.byte_length,
        candidate.claimed_cost,
        candidate.claimed_cycles,
        candidate.claimed_area,
        candidate.claimed_instructions,
    )
    return artifact_row, evidence_row


def _aggregate_group(group: list[_IngestedCandidate]) -> ArtifactRecord:
    first = group[0]
    puzzle_ids = {item.candidate.puzzle_id for item in group}
    formats = {item.candidate.artifact_format for item in group}
    if len(puzzle_ids) != 1:
        raise ArtifactIngestionError(
            f"{first.artifact_id}: same artifact digest associated with different puzzle IDs"
        )
    if len(formats) != 1:
        raise ArtifactIngestionError(f"{first.artifact_id}: conflicting artifact formats")
    if len({item.artifact.byte_length for item in group}) != 1:
        raise ArtifactIngestionError(f"{first.artifact_id}: inconsistent byte lengths")
    if len({item.artifact.object_key for item in group}) != 1:
        raise ArtifactIngestionError(f"{first.artifact_id}: inconsistent object keys")
    return ArtifactRecord(
        first.candidate.artifact_kind,
        first.artifact_id,
        next(iter(puzzle_ids)),
        first.artifact.sha256,
        first.artifact.byte_length,
        next(iter(formats)),
        _aggregate_rights(item.candidate.artifact_receipt.rights_status for item in group),
        first.artifact.object_key,
    )


def _provenance_sort_key(row: ArtifactProvenance) -> tuple[tuple[int, str], ...]:
    return tuple(
        (0, "") if value is None else (1, str(value))
        for value in (
            row.artifact_id,
            row.puzzle_id,
            row.source_role,
            row.source_id,
            row.source_revision,
            row.source_path,
            row.source_object_id,
            row.source_url,
            row.author,
            row.retrieved_at,
            row.rights_status,
            row.observed_sha256,
            row.source_evidence_sha256,
            row.source_evidence_byte_length,
            row.claimed_cost,
            row.claimed_cycles,
            row.claimed_area,
            row.claimed_instructions,
        )
    )


def ingest_artifacts(
    candidates: Iterable[ObservedArtifactCandidate],
    store: ContentStore,
) -> IngestionResult:
    materialized = [_validate_candidate(candidate, store) for candidate in candidates]
    artifact_associations: dict[tuple[str, str, str], tuple[object, ...]] = {}
    evidence_associations: dict[tuple[str, str, str, str | None], str] = {}
    for item in materialized:
        candidate = item.candidate
        receipt_key = _receipt_identity(candidate.artifact_receipt)
        association = (
            candidate.artifact_kind,
            candidate.puzzle_id,
            candidate.artifact_format,
            candidate.artifact_receipt.sha256,
            candidate.artifact_receipt.byte_length,
        )
        previous = artifact_associations.setdefault(receipt_key, association)
        if previous != association:
            raise ArtifactIngestionError(
                f"{candidate.puzzle_id}: artifact receipt identity has conflicting association"
            )
        evidence_receipt = candidate.evidence_receipt or candidate.artifact_receipt
        evidence_key = (*_receipt_identity(evidence_receipt), candidate.source_object_id)
        previous_artifact = evidence_associations.setdefault(evidence_key, item.artifact_id)
        if previous_artifact != item.artifact_id:
            raise ArtifactIngestionError(
                f"{candidate.puzzle_id}: evidence assertion identity supports multiple artifacts"
            )

    groups: dict[tuple[str, str], list[_IngestedCandidate]] = {}
    for item in materialized:
        groups.setdefault((item.candidate.artifact_kind, item.artifact.sha256), []).append(item)

    artifacts = [_aggregate_group(group) for group in groups.values()]
    provenance: set[ArtifactProvenance] = set()
    for item in materialized:
        provenance.update(_provenance_rows(item))
    return IngestionResult(
        artifacts=tuple(sorted(artifacts, key=lambda row: (row.artifact_kind, row.artifact_id))),
        provenance=tuple(sorted(provenance, key=_provenance_sort_key)),
    )
