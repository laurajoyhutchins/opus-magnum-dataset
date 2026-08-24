# Content-Addressed Artifact Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic exact-byte ingestion layer that materializes puzzle and solution artifacts into a SHA-256 content-addressed object store while preserving source provenance and performing exact-byte deduplication.

**Architecture:** Add one source-agnostic module, `src/opus_corpus/ingestion.py`. Adapter-specific orchestration wraps discovered files as `ObservedArtifactCandidate` values; ingestion streams each candidate payload once into a temporary object while hashing, atomically publishes the exact bytes by digest, then folds candidates into deterministic `ArtifactRecord` and `ArtifactProvenance` tuples. Verification, normalization, observation projection, release JSONL generation, and adapter behavior remain unchanged.

**Tech Stack:** Python 3.12 standard library (`dataclasses`, `hashlib`, `os`, `pathlib`, `stat`, `tempfile`, typing), pytest 9.0.2, Ruff 0.12.12.

**Spec:** `docs/superpowers/specs/2026-08-24-artifact-ingestion-design.md`

## Global Constraints

- Exact source bytes are the v1 deduplication boundary; do not parse, normalize, decompress, or reserialize payloads before hashing.
- Artifact IDs are deterministic: `om.puzzle-artifact.sha256.<digest>` for puzzles and `om.solution.sha256.<digest>` for solutions.
- Physical object keys use `sha256/<first-two-hex>/<digest>` and are independent of source identity or local path.
- Stream each candidate source payload once into a temporary file while computing SHA-256 and byte length; do not hash then reread the source for publication.
- Local absolute paths may be used only to read payloads. They must not enter artifact IDs, canonical records, provenance records, sort keys, or exported values.
- Exact duplicate source assertions may collapse; distinct provenance assertions must remain distinct even when they point to the same artifact.
- Artifact-level rights aggregation is conservative: `local_fetch_only` outranks `unknown`, which outranks `redistributable`; provenance-level rights remain unchanged.
- Source-claimed metrics remain provenance facts and never become verifier-computed metrics in this layer.
- Fail closed on ambiguous artifact identity, changed or unreadable source payloads, conflicting formats, and corrupt pre-existing object-store blobs.
- Do not modify source adapters, release schemas, `release.py`, normalization code, verifier behavior, or Hugging Face export in this slice.
- `retrieved_at` is caller-supplied stable provenance. Never synthesize it from wall-clock build time.
- No new third-party dependencies.

---

### Task 1: Typed contracts and one-pass content-addressed publication

**Files:**
- Create: `src/opus_corpus/ingestion.py`
- Create: `tests/test_ingestion.py`

**Interfaces:**
- Produces: `ArtifactIngestionError(RuntimeError)`
- Produces: `ObservedArtifactCandidate`
- Produces: `ArtifactRecord`
- Produces: `ArtifactProvenance`
- Produces: `IngestionResult`
- Produces: `ingest_artifacts(candidates: Iterable[ObservedArtifactCandidate], object_root: Path) -> IngestionResult`
- Internal helper: `_artifact_id(artifact_kind: str, digest: str) -> str`
- Internal helper: `_object_key(digest: str) -> str`
- Internal helper: `_source_signature(path: Path) -> tuple[int, int, int, int, int]`
- Internal helper: `_stream_to_object(candidate: ObservedArtifactCandidate, object_root: Path) -> tuple[str, int, str]`, returning `(sha256, byte_length, object_key)`

- [ ] **Step 1: Write the failing single-artifact tests**

Create `tests/test_ingestion.py` with fixed local bytes and assertions for exact digest, byte length, ID namespace, object key, stored bytes, and provenance fields:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from opus_corpus.ingestion import ObservedArtifactCandidate, ingest_artifacts


def _candidate(path: Path, **overrides: object) -> ObservedArtifactCandidate:
    values: dict[str, object] = {
        "artifact_kind": "solution",
        "puzzle_id": "om.puzzle.0001",
        "path": path,
        "artifact_format": "solution",
        "rights_status": "local_fetch_only",
        "source_id": "om-archive",
        "source_revision": "revision-a",
        "source_object_id": None,
        "source_path": "CHAPTER_1/P001/example.solution",
        "source_url": None,
        "author": "Example Author",
        "retrieved_at": "2026-08-24T12:00:00Z",
        "claimed_cost": 20,
        "claimed_cycles": 40,
        "claimed_area": 10,
        "claimed_instructions": 6,
    }
    values.update(overrides)
    return ObservedArtifactCandidate(**values)  # type: ignore[arg-type]


def test_ingest_solution_streams_exact_bytes_into_content_store(tmp_path: Path) -> None:
    source = tmp_path / "source.solution"
    payload = b"exact-solution-bytes\x00\xff\n"
    source.write_bytes(payload)
    object_root = tmp_path / "objects"
    digest = hashlib.sha256(payload).hexdigest()

    result = ingest_artifacts([_candidate(source)], object_root)

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_kind == "solution"
    assert artifact.artifact_id == f"om.solution.sha256.{digest}"
    assert artifact.puzzle_id == "om.puzzle.0001"
    assert artifact.sha256 == digest
    assert artifact.byte_length == len(payload)
    assert artifact.artifact_format == "solution"
    assert artifact.rights_status == "local_fetch_only"
    assert artifact.object_key == f"sha256/{digest[:2]}/{digest}"
    assert (object_root / artifact.object_key).read_bytes() == payload

    assert len(result.provenance) == 1
    provenance = result.provenance[0]
    assert provenance.artifact_id == artifact.artifact_id
    assert provenance.puzzle_id == "om.puzzle.0001"
    assert provenance.source_id == "om-archive"
    assert provenance.source_path == "CHAPTER_1/P001/example.solution"
    assert provenance.claimed_cost == 20
    assert provenance.rights_status == "local_fetch_only"


def test_ingest_puzzle_uses_distinct_artifact_namespace(tmp_path: Path) -> None:
    source = tmp_path / "source.puzzle"
    payload = b"exact-puzzle-bytes"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    result = ingest_artifacts(
        [
            _candidate(
                source,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="omsim",
                source_path="test/puzzle/P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            )
        ],
        tmp_path / "objects",
    )

    assert result.artifacts[0].artifact_id == f"om.puzzle-artifact.sha256.{digest}"
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

Run:

```bash
uv run pytest tests/test_ingestion.py -q
```

Expected: collection/import failure because `opus_corpus.ingestion` does not exist yet.

- [ ] **Step 3: Implement the typed data model and identity helpers**

Create `src/opus_corpus/ingestion.py` with frozen dataclasses. Keep the public records free of local absolute paths except for the input candidate:

```python
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
```

- [ ] **Step 4: Implement one-pass source streaming and atomic object publication**

Use one source file handle to stream bytes into a temporary file under the same object root while hashing and counting. Compare source stat metadata before and after streaming to detect mutation during ingestion. Publish with `os.link` so an existing target is never overwritten:

```python
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
```

This helper may reread a pre-existing content-store object to verify corruption, but it must not reread the source candidate payload.

- [ ] **Step 5: Implement the minimal single-candidate ingestion path**

For this task, support normal candidates without aggregation complexity yet. Task 2 will replace the temporary linear accumulation with deterministic grouping:

```python
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
```

- [ ] **Step 6: Run focused tests and lint**

```bash
uv run pytest tests/test_ingestion.py -q
uv run ruff check src/opus_corpus/ingestion.py tests/test_ingestion.py
```

Expected: both commands pass.

- [ ] **Step 7: Commit the independently working one-artifact ingestion primitive**

```bash
git add src/opus_corpus/ingestion.py tests/test_ingestion.py
git commit -m "feat: add exact-byte artifact ingestion"
```

---

### Task 2: Exact-byte deduplication, provenance preservation, rights folding, and deterministic order

**Files:**
- Modify: `src/opus_corpus/ingestion.py`
- Modify: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: `ObservedArtifactCandidate`, `ArtifactRecord`, `ArtifactProvenance`, `IngestionResult`, `_stream_to_object`, `_artifact_id`, `_provenance`
- Produces internal: `_IngestedCandidate`
- Produces: `_aggregate_rights(statuses: Iterable[str]) -> str`
- Produces: deterministic `ingest_artifacts(...)` returning one artifact per `(artifact_kind, digest)` and all distinct provenance assertions

- [ ] **Step 1: Add failing deduplication and provenance tests**

Append these tests:

```python
def test_identical_solution_bytes_deduplicate_without_losing_provenance(tmp_path: Path) -> None:
    first = tmp_path / "first.solution"
    second = tmp_path / "second.solution"
    first.write_bytes(b"same bytes")
    second.write_bytes(b"same bytes")

    result = ingest_artifacts(
        [
            _candidate(first, source_id="om-archive", source_path="archive/a.solution"),
            _candidate(
                second,
                source_id="om-leaderboard",
                source_path="leaderboard/a.solution",
                claimed_cost=19,
            ),
        ],
        tmp_path / "objects",
    )

    assert len(result.artifacts) == 1
    assert len(result.provenance) == 2
    assert {row.source_id for row in result.provenance} == {"om-archive", "om-leaderboard"}
    assert {row.claimed_cost for row in result.provenance} == {19, 20}
    assert not hasattr(result.artifacts[0], "claimed_cost")


def test_identical_puzzle_bytes_deduplicate_without_losing_provenance(tmp_path: Path) -> None:
    first = tmp_path / "first.puzzle"
    second = tmp_path / "second.puzzle"
    first.write_bytes(b"same puzzle")
    second.write_bytes(b"same puzzle")

    result = ingest_artifacts(
        [
            _candidate(
                first,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="omsim",
                source_path="fixtures/P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            ),
            _candidate(
                second,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="official-game",
                source_path="P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            ),
        ],
        tmp_path / "objects",
    )

    assert len(result.artifacts) == 1
    assert {row.source_id for row in result.provenance} == {"omsim", "official-game"}


def test_exact_duplicate_provenance_assertions_collapse(tmp_path: Path) -> None:
    source = tmp_path / "same.solution"
    source.write_bytes(b"same bytes")
    candidate = _candidate(source)

    result = ingest_artifacts([candidate, candidate], tmp_path / "objects")

    assert len(result.artifacts) == 1
    assert len(result.provenance) == 1


def test_different_bytes_never_deduplicate(tmp_path: Path) -> None:
    first = tmp_path / "first.solution"
    second = tmp_path / "second.solution"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    result = ingest_artifacts(
        [_candidate(first), _candidate(second, source_path="other.solution")],
        tmp_path / "objects",
    )

    assert len(result.artifacts) == 2
```

- [ ] **Step 2: Add failing rights aggregation tests**

```python
def test_artifact_rights_local_fetch_only_outranks_other_statuses(tmp_path: Path) -> None:
    sources = [tmp_path / name for name in ("a.solution", "b.solution", "c.solution")]
    for source in sources:
        source.write_bytes(b"same")

    result = ingest_artifacts(
        [
            _candidate(sources[0], source_id="a", source_path="a", rights_status="redistributable"),
            _candidate(sources[1], source_id="b", source_path="b", rights_status="unknown"),
            _candidate(sources[2], source_id="c", source_path="c", rights_status="local_fetch_only"),
        ],
        tmp_path / "objects",
    )

    assert result.artifacts[0].rights_status == "local_fetch_only"
    assert {row.rights_status for row in result.provenance} == {
        "redistributable",
        "unknown",
        "local_fetch_only",
    }


def test_artifact_rights_unknown_outranks_redistributable(tmp_path: Path) -> None:
    first = tmp_path / "a.solution"
    second = tmp_path / "b.solution"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    result = ingest_artifacts(
        [
            _candidate(first, source_id="a", source_path="a", rights_status="redistributable"),
            _candidate(second, source_id="b", source_path="b", rights_status="unknown"),
        ],
        tmp_path / "objects",
    )

    assert result.artifacts[0].rights_status == "unknown"
```

- [ ] **Step 3: Add failing deterministic-order and local-root-independence tests**

```python
def test_logical_output_is_independent_of_candidate_and_local_path_order(tmp_path: Path) -> None:
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    left_root.mkdir()
    right_root.mkdir()
    (left_root / "a.solution").write_bytes(b"alpha")
    (left_root / "b.solution").write_bytes(b"beta")
    (right_root / "renamed-one.solution").write_bytes(b"alpha")
    (right_root / "renamed-two.solution").write_bytes(b"beta")

    left = ingest_artifacts(
        [
            _candidate(left_root / "b.solution", source_id="b", source_path="stable/b"),
            _candidate(left_root / "a.solution", source_id="a", source_path="stable/a"),
        ],
        tmp_path / "objects-left",
    )
    right = ingest_artifacts(
        [
            _candidate(right_root / "renamed-one.solution", source_id="a", source_path="stable/a"),
            _candidate(right_root / "renamed-two.solution", source_id="b", source_path="stable/b"),
        ],
        tmp_path / "objects-right",
    )

    assert left == right
```

- [ ] **Step 4: Run the new tests and confirm they fail against Task 1 behavior**

```bash
uv run pytest tests/test_ingestion.py -q
```

Expected: failures showing duplicate artifacts/provenance, unaggregated rights, and order-dependent tuples.

- [ ] **Step 5: Add the internal materialized-candidate type and deterministic sort/fold helpers**

```python
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
```

- [ ] **Step 6: Replace linear accumulation with exact-byte grouping**

Materialize every candidate first, then group by semantic artifact namespace plus digest. Task 3 will add the conflict checks before each aggregate row is created:

```python
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
        first = group[0]
        candidate = first.candidate
        artifacts.append(
            ArtifactRecord(
                artifact_kind=candidate.artifact_kind,
                artifact_id=first.artifact_id,
                puzzle_id=candidate.puzzle_id,
                sha256=first.sha256,
                byte_length=first.byte_length,
                artifact_format=candidate.artifact_format,
                rights_status=_aggregate_rights(item.candidate.rights_status for item in group),
                object_key=first.object_key,
            )
        )
        provenance.update(_provenance(item.candidate, item.artifact_id) for item in group)

    return IngestionResult(
        artifacts=tuple(sorted(artifacts, key=_artifact_sort_key)),
        provenance=tuple(sorted(provenance, key=_provenance_sort_key)),
    )
```

- [ ] **Step 7: Run focused tests and lint**

```bash
uv run pytest tests/test_ingestion.py -q
uv run ruff check src/opus_corpus/ingestion.py tests/test_ingestion.py
```

Expected: all Task 1 and Task 2 tests pass.

- [ ] **Step 8: Commit deduplication and deterministic aggregation**

```bash
git add src/opus_corpus/ingestion.py tests/test_ingestion.py
git commit -m "feat: deduplicate ingested artifacts"
```

---

### Task 3: Fail-closed conflicts, source mutation detection, and corrupt-store protection

**Files:**
- Modify: `src/opus_corpus/ingestion.py`
- Modify: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: `_IngestedCandidate` groups from Task 2
- Produces internal: `_aggregate_group(group: list[_IngestedCandidate]) -> ArtifactRecord`
- Preserves: puzzle and solution namespaces remain semantically separate even when physical bytes are identical

- [ ] **Step 1: Add failing semantic conflict tests**

Add `pytest` and `ArtifactIngestionError` imports, then append:

```python
import pytest

from opus_corpus.ingestion import ArtifactIngestionError


def test_same_solution_digest_for_different_puzzles_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "a.solution"
    second = tmp_path / "b.solution"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    with pytest.raises(ArtifactIngestionError, match="different puzzle IDs"):
        ingest_artifacts(
            [
                _candidate(first, puzzle_id="om.puzzle.0001"),
                _candidate(second, puzzle_id="om.puzzle.0002", source_path="b.solution"),
            ],
            tmp_path / "objects",
        )


def test_same_puzzle_digest_for_different_puzzles_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "a.puzzle"
    second = tmp_path / "b.puzzle"
    first.write_bytes(b"same puzzle bytes")
    second.write_bytes(b"same puzzle bytes")

    with pytest.raises(ArtifactIngestionError, match="different puzzle IDs"):
        ingest_artifacts(
            [
                _candidate(
                    first,
                    artifact_kind="puzzle",
                    artifact_format="puzzle",
                    puzzle_id="om.puzzle.0001",
                    claimed_cost=None,
                    claimed_cycles=None,
                    claimed_area=None,
                    claimed_instructions=None,
                ),
                _candidate(
                    second,
                    artifact_kind="puzzle",
                    artifact_format="puzzle",
                    puzzle_id="om.puzzle.0002",
                    source_path="b.puzzle",
                    claimed_cost=None,
                    claimed_cycles=None,
                    claimed_area=None,
                    claimed_instructions=None,
                ),
            ],
            tmp_path / "objects",
        )


def test_same_artifact_digest_with_conflicting_formats_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "a.solution"
    second = tmp_path / "b.solution"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    with pytest.raises(ArtifactIngestionError, match="conflicting artifact formats"):
        ingest_artifacts(
            [
                _candidate(first, artifact_format="solution"),
                _candidate(second, artifact_format="legacy-solution", source_path="b.solution"),
            ],
            tmp_path / "objects",
        )
```

- [ ] **Step 2: Add a test proving puzzle and solution namespaces can share one physical digest object**

```python
def test_same_bytes_in_puzzle_and_solution_namespaces_share_object_not_id(tmp_path: Path) -> None:
    puzzle = tmp_path / "a.puzzle"
    solution = tmp_path / "a.solution"
    puzzle.write_bytes(b"identical physical bytes")
    solution.write_bytes(b"identical physical bytes")

    result = ingest_artifacts(
        [
            _candidate(
                puzzle,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="omsim",
                source_path="puzzle/P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            ),
            _candidate(solution, source_path="solution/P007.solution"),
        ],
        tmp_path / "objects",
    )

    by_kind = {artifact.artifact_kind: artifact for artifact in result.artifacts}
    assert set(by_kind) == {"puzzle", "solution"}
    assert by_kind["puzzle"].artifact_id != by_kind["solution"].artifact_id
    assert by_kind["puzzle"].sha256 == by_kind["solution"].sha256
    assert by_kind["puzzle"].object_key == by_kind["solution"].object_key
```

- [ ] **Step 3: Add failing missing, non-file, and unreadable-source tests**

```python
def test_missing_payload_fails_explicitly(tmp_path: Path) -> None:
    with pytest.raises(ArtifactIngestionError, match="cannot stat source payload"):
        ingest_artifacts([_candidate(tmp_path / "missing.solution")], tmp_path / "objects")


def test_directory_payload_fails_explicitly(tmp_path: Path) -> None:
    source = tmp_path / "directory"
    source.mkdir()
    with pytest.raises(ArtifactIngestionError, match="not a file"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")


def test_unreadable_payload_is_wrapped_as_ingestion_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.solution"
    source.write_bytes(b"payload")
    real_open = Path.open

    def fail_source_open(self: Path, *args: object, **kwargs: object):
        if self == source:
            raise PermissionError("denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_source_open)

    with pytest.raises(ArtifactIngestionError, match="cannot ingest source payload"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")
```

- [ ] **Step 4: Add failing corrupt-store protection test**

```python
def test_corrupt_existing_content_object_fails_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.solution"
    source.write_bytes(b"good bytes")
    digest = hashlib.sha256(b"good bytes").hexdigest()
    object_path = tmp_path / "objects" / f"sha256/{digest[:2]}/{digest}"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"corrupt bytes")

    with pytest.raises(ArtifactIngestionError, match="does not match its digest"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")

    assert object_path.read_bytes() == b"corrupt bytes"
```

- [ ] **Step 5: Add a deterministic source-mutation test at the helper boundary**

Import the module itself so the private signature helper can be monkeypatched without threads or timing:

```python
import opus_corpus.ingestion as ingestion


def test_source_change_during_stream_fails_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.solution"
    source.write_bytes(b"payload")
    original = ingestion._source_signature(source)
    changed = (original[0], original[1], original[2], original[3], original[4] + 1)
    signatures = iter((original, changed))

    monkeypatch.setattr(ingestion, "_source_signature", lambda path: next(signatures))

    with pytest.raises(ArtifactIngestionError, match="changed during ingestion"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")

    digest = hashlib.sha256(b"payload").hexdigest()
    assert not (tmp_path / "objects" / f"sha256/{digest[:2]}/{digest}").exists()
```

- [ ] **Step 6: Run the conflict/error tests and confirm the red state**

```bash
uv run pytest tests/test_ingestion.py -q
```

Expected: the puzzle-ID and format-conflict cases fail against Task 2 behavior. Existing source/store guards may already satisfy some error tests; those remain regression locks.

- [ ] **Step 7: Implement group-level identity conflict checks**

Add one helper and use it from `ingest_artifacts` instead of building the aggregate row from `group[0]` directly:

```python
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
```

Then change the aggregation loop to:

```python
for group in groups.values():
    artifacts.append(_aggregate_group(group))
    provenance.update(_provenance(item.candidate, item.artifact_id) for item in group)
```

- [ ] **Step 8: Verify source/store behavior is fail closed**

Read `_stream_to_object` against the tests from Steps 3-5. Its final behavior must be exactly:

```python
# Source identity guard
before = _source_signature(source)
if not stat.S_ISREG(before[2]):
    raise ArtifactIngestionError(...)
# stream source once into temp while hashing
# fsync temp
after = _source_signature(source)
if before != after:
    raise ArtifactIngestionError(...)
# if target exists, verify it; never replace it
# otherwise os.link(temp_path, target)
# on FileExistsError, verify the concurrent winner
# always unlink temp_path in finally
```

Do not add code that deletes, rewrites, or heuristically repairs a corrupt content object.

- [ ] **Step 9: Run focused tests and lint**

```bash
uv run pytest tests/test_ingestion.py -q
uv run ruff check src/opus_corpus/ingestion.py tests/test_ingestion.py
```

Expected: all ingestion tests pass and Ruff reports no findings.

- [ ] **Step 10: Commit fail-closed invariants**

```bash
git add src/opus_corpus/ingestion.py tests/test_ingestion.py
git commit -m "test: enforce artifact ingestion invariants"
```

---

### Task 4: Acceptance regression and stacked-PR readiness

**Files:**
- Modify only if a concrete regression requires it: `src/opus_corpus/ingestion.py`, `tests/test_ingestion.py`
- No planned changes to adapters, release schemas, release builder, CLI, or fixtures

**Interfaces:**
- Consumes: completed ingestion API from Tasks 1-3
- Produces: a branch whose full repository validation matches `.github/workflows/validate.yml`

- [ ] **Step 1: Run the complete ingestion test file in verbose mode**

```bash
uv run pytest tests/test_ingestion.py -v
```

Expected: every artifact-ingestion case passes, including stable IDs, exact-byte deduplication, distinct-byte separation, rights folding, namespace separation, conflict failures, corruption protection, provenance deduplication, and directory/order independence.

- [ ] **Step 2: Run repository lint**

```bash
uv run ruff check .
```

Expected: exit 0 with no lint findings.

- [ ] **Step 3: Run the full test suite**

```bash
uv run pytest -q
```

Expected: exit 0. Existing adapter, collection, release, serialization, payload, and publication tests remain unchanged and green.

- [ ] **Step 4: Validate the frozen collection inventory**

```bash
uv run opus-corpus collections validate
```

Expected: exit 0 with the existing frozen `base-game-2026-06-16` collection accepted.

- [ ] **Step 5: Reproduce the tiny release CI smoke test**

```bash
rm -rf .tmp-release .tmp-stage
uv run opus-corpus release build base-game-2026-06-16 \
  --input fixtures/tiny-corpus \
  --output .tmp-release \
  --payload-policy metadata-only
uv run opus-corpus release validate base-game-2026-06-16 --output .tmp-release
uv run opus-corpus release stage base-game-2026-06-16 \
  --output .tmp-release \
  --destination .tmp-stage
```

Expected: all three commands exit 0. This proves the new module did not alter the existing release contract.

- [ ] **Step 6: Inspect the branch diff for scope containment**

```bash
git diff feature/github-source-adapters...HEAD -- \
  src/opus_corpus/ingestion.py \
  tests/test_ingestion.py \
  docs/superpowers/specs/2026-08-24-artifact-ingestion-design.md \
  docs/superpowers/plans/2026-08-24-artifact-ingestion.md
```

Expected: the stacked slice contains only the ingestion implementation/tests plus its approved spec and plan. If the complete branch diff contains unrelated files, remove or separately account for them before opening the PR.

- [ ] **Step 7: Commit any test-driven acceptance correction, otherwise create no commit**

If Steps 1-6 expose a concrete code/test defect, fix only that defect and commit it:

```bash
git add src/opus_corpus/ingestion.py tests/test_ingestion.py
git commit -m "fix: satisfy artifact ingestion acceptance"
```

If all checks already pass, do not create an empty commit.

- [ ] **Step 8: Open a draft stacked PR against the adapter branch**

Create the pull request with exactly these metadata values:

```text
base: feature/github-source-adapters
head: feature/artifact-ingestion
draft: true
title: Add content-addressed artifact ingestion
```

Use this body:

```markdown
Implements the deterministic exact-byte ingestion boundary downstream of source adapters.

- Adds source-agnostic observed-artifact, artifact-record, provenance, and ingestion-result contracts.
- Streams source bytes once into a SHA-256 content-addressed local object store and publishes without overwriting existing digest objects.
- Uses content-derived puzzle/solution artifact IDs and exact-byte-only deduplication.
- Preserves distinct source provenance and source-claimed metrics while conservatively aggregating artifact rights.
- Fails closed on conflicting puzzle identity, conflicting formats, changed source payloads, and corrupt object-store state.
- Keeps verifier execution, normalization, observation projection, release JSONL generation, and adapter-specific orchestration out of scope.

Validation: repository lint, full tests, frozen collection validation, and tiny release build/validate/stage all pass.
```

Do not retarget PR #10 and do not merge either PR as part of this plan.
