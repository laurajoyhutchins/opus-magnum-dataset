from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class ArtifactIngestionError(RuntimeError):
    """Raised when exact-byte artifact ingestion cannot proceed deterministically."""


@dataclass(frozen=True)
class ObservedArtifactCandidate:
    artifact_kind: str
    puzzle_id: str
    path: Path
    artifact_format: str
    rights_status: str
    source_id: str
    source_revision: str | None = None
    source_object_id: str | None = None
    source_path: str | None = None
    source_url: str | None = None
    author: str | None = None
    retrieved_at: str | None = None
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
    source_id: str
    source_revision: str | None
    source_object_id: str | None
    source_path: str | None
    source_url: str | None
    author: str | None
    retrieved_at: str | None
    claimed_cost: int | None
    claimed_cycles: int | None
    claimed_area: int | None
    claimed_instructions: int | None
    rights_status: str


@dataclass(frozen=True)
class IngestionResult:
    artifacts: tuple[ArtifactRecord, ...]
    provenance: tuple[ArtifactProvenance, ...]


@dataclass(frozen=True)
class _IngestedCandidate:
    candidate: ObservedArtifactCandidate
    artifact_id: str
    sha256: str
    byte_length: int
    object_key: str


_RIGHTS_RANK = {
    "redistributable": 0,
    "unknown": 1,
    "local_fetch_only": 2,
}


def _artifact_id(artifact_kind: str, digest: str) -> str:
    if artifact_kind == "puzzle":
        return f"om.puzzle-artifact.sha256.{digest}"
    if artifact_kind == "solution":
        return f"om.solution.sha256.{digest}"
    raise ArtifactIngestionError(f"unsupported artifact kind {artifact_kind!r}")


def _object_key(digest: str) -> str:
    return f"sha256/{digest[:2]}/{digest}"


def _source_signature(path: Path) -> tuple[int, int, int, int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stream_to_object(
    candidate: ObservedArtifactCandidate,
    object_root: Path,
) -> tuple[str, int, str]:
    source = Path(candidate.path)
    try:
        before = _source_signature(source)
    except OSError as exc:
        raise ArtifactIngestionError(
            f"{candidate.artifact_kind} {candidate.puzzle_id} from "
            f"{candidate.source_id}: cannot stat source payload"
        ) from exc
    if not stat.S_ISREG(before[2]):
        raise ArtifactIngestionError(
            f"{candidate.artifact_kind} {candidate.puzzle_id} from "
            f"{candidate.source_id}: source payload is not a file"
        )

    object_root = Path(object_root)
    temp_root = object_root / ".tmp"
    temp_path: Path | None = None
    try:
        temp_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        byte_length = 0
        with source.open("rb") as source_handle, tempfile.NamedTemporaryFile(
            dir=temp_root,
            prefix="ingest-",
            delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)
            for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                digest.update(chunk)
                byte_length += len(chunk)
                temp_handle.write(chunk)
            temp_handle.flush()
            os.fsync(temp_handle.fileno())

        after = _source_signature(source)
        if before != after:
            raise ArtifactIngestionError(
                f"{candidate.artifact_kind} {candidate.puzzle_id} from "
                f"{candidate.source_id}: source payload changed during ingestion"
            )

        hex_digest = digest.hexdigest()
        object_key = _object_key(hex_digest)
        target = object_root / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or _sha256_path(target) != hex_digest:
                raise ArtifactIngestionError(
                    f"content store object {object_key} does not match its digest"
                )
        else:
            try:
                os.link(temp_path, target)
            except FileExistsError:
                if not target.is_file() or _sha256_path(target) != hex_digest:
                    raise ArtifactIngestionError(
                        f"content store object {object_key} does not match its digest"
                    )
        return hex_digest, byte_length, object_key
    except ArtifactIngestionError:
        raise
    except OSError as exc:
        raise ArtifactIngestionError(
            f"{candidate.artifact_kind} {candidate.puzzle_id} from "
            f"{candidate.source_id}: cannot ingest source payload"
        ) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _provenance(candidate: ObservedArtifactCandidate, artifact_id: str) -> ArtifactProvenance:
    return ArtifactProvenance(
        artifact_id=artifact_id,
        puzzle_id=candidate.puzzle_id,
        source_id=candidate.source_id,
        source_revision=candidate.source_revision,
        source_object_id=candidate.source_object_id,
        source_path=candidate.source_path,
        source_url=candidate.source_url,
        author=candidate.author,
        retrieved_at=candidate.retrieved_at,
        claimed_cost=candidate.claimed_cost,
        claimed_cycles=candidate.claimed_cycles,
        claimed_area=candidate.claimed_area,
        claimed_instructions=candidate.claimed_instructions,
        rights_status=candidate.rights_status,
    )


def _aggregate_rights(statuses: Iterable[str]) -> str:
    values = tuple(statuses)
    if not values:
        raise ArtifactIngestionError("invalid or empty rights status set")
    try:
        return max(values, key=_RIGHTS_RANK.__getitem__)
    except KeyError as exc:
        raise ArtifactIngestionError(f"invalid rights status {exc.args[0]!r}") from exc


def _artifact_sort_key(record: ArtifactRecord) -> tuple[str, str]:
    return record.artifact_kind, record.artifact_id


def _provenance_sort_key(row: ArtifactProvenance) -> tuple[str, ...]:
    return tuple(
        "" if value is None else str(value)
        for value in (
            row.artifact_id,
            row.puzzle_id,
            row.source_id,
            row.source_revision,
            row.source_object_id,
            row.source_path,
            row.source_url,
            row.author,
            row.retrieved_at,
            row.claimed_cost,
            row.claimed_cycles,
            row.claimed_area,
            row.claimed_instructions,
            row.rights_status,
        )
    )


def _aggregate_group(group: list[_IngestedCandidate]) -> ArtifactRecord:
    first = group[0]
    artifact_id = first.artifact_id

    puzzle_ids = {item.candidate.puzzle_id for item in group}
    if len(puzzle_ids) != 1:
        raise ArtifactIngestionError(
            f"{artifact_id}: same artifact digest associated with different puzzle IDs"
        )

    formats = {item.candidate.artifact_format for item in group}
    if len(formats) != 1:
        raise ArtifactIngestionError(f"{artifact_id}: conflicting artifact formats")

    byte_lengths = {item.byte_length for item in group}
    if len(byte_lengths) != 1:
        raise ArtifactIngestionError(f"{artifact_id}: conflicting byte lengths")

    object_keys = {item.object_key for item in group}
    if len(object_keys) != 1:
        raise ArtifactIngestionError(f"{artifact_id}: conflicting object keys")

    return ArtifactRecord(
        artifact_kind=first.candidate.artifact_kind,
        artifact_id=artifact_id,
        puzzle_id=next(iter(puzzle_ids)),
        sha256=first.sha256,
        byte_length=next(iter(byte_lengths)),
        artifact_format=next(iter(formats)),
        rights_status=_aggregate_rights(item.candidate.rights_status for item in group),
        object_key=next(iter(object_keys)),
    )


def ingest_artifacts(
    candidates: Iterable[ObservedArtifactCandidate],
    object_root: Path,
) -> IngestionResult:
    materialized: list[_IngestedCandidate] = []
    for candidate in candidates:
        digest, byte_length, object_key = _stream_to_object(candidate, object_root)
        materialized.append(
            _IngestedCandidate(
                candidate=candidate,
                artifact_id=_artifact_id(candidate.artifact_kind, digest),
                sha256=digest,
                byte_length=byte_length,
                object_key=object_key,
            )
        )

    groups: dict[tuple[str, str], list[_IngestedCandidate]] = {}
    for fact in materialized:
        key = (fact.candidate.artifact_kind, fact.sha256)
        groups.setdefault(key, []).append(fact)

    artifacts: list[ArtifactRecord] = []
    provenance: set[ArtifactProvenance] = set()
    for group in groups.values():
        artifacts.append(_aggregate_group(group))
        provenance.update(_provenance(item.candidate, item.artifact_id) for item in group)

    return IngestionResult(
        artifacts=tuple(sorted(artifacts, key=_artifact_sort_key)),
        provenance=tuple(sorted(provenance, key=_provenance_sort_key)),
    )
