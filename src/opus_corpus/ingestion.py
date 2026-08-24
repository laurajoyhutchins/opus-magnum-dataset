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


def ingest_artifacts(
    candidates: Iterable[ObservedArtifactCandidate],
    store: ContentStore,
) -> IngestionResult:
    artifacts: list[ArtifactRecord] = []
    for candidate in candidates:
        item = _validate_candidate(candidate, store)
        artifacts.append(
            ArtifactRecord(
                candidate.artifact_kind,
                item.artifact_id,
                candidate.puzzle_id,
                item.artifact.sha256,
                item.artifact.byte_length,
                candidate.artifact_format,
                candidate.artifact_receipt.rights_status,
                item.artifact.object_key,
            )
        )
    return IngestionResult(tuple(artifacts), ())
