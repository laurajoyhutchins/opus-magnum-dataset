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


def ingest_artifacts(
    candidates: Iterable[ObservedArtifactCandidate],
    object_root: Path,
) -> IngestionResult:
    artifacts: list[ArtifactRecord] = []
    provenance: list[ArtifactProvenance] = []
    for candidate in candidates:
        digest, byte_length, object_key = _stream_to_object(candidate, object_root)
        artifact_id = _artifact_id(candidate.artifact_kind, digest)
        artifacts.append(
            ArtifactRecord(
                artifact_kind=candidate.artifact_kind,
                artifact_id=artifact_id,
                puzzle_id=candidate.puzzle_id,
                sha256=digest,
                byte_length=byte_length,
                artifact_format=candidate.artifact_format,
                rights_status=candidate.rights_status,
                object_key=object_key,
            )
        )
        provenance.append(_provenance(candidate, artifact_id))
    return IngestionResult(tuple(artifacts), tuple(provenance))
