# Shared Content Store and Artifact Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the landed acquisition cache onto one authoritative exact-byte `ContentStore`, then materialize deterministic artifact and provenance facts exclusively from persisted cache receipts.

**Architecture:** `ContentStore` becomes the sole owner of the existing `objects/sha256/<2>/<62>` layout and object integrity verification. `ContentAddressedCache` keeps acquisition receipt semantics while delegating bytes to that store. A new source-agnostic ingestion module consumes `CacheReceipt` values, validates every referenced source object through `ContentStore.require`, and derives artifact/provenance facts without opening source files or publishing bytes.

**Tech Stack:** Python 3.12 standard library (`dataclasses`, `os`, `pathlib`, `re`, `stat`, `tempfile`), existing repository hashing helpers, pytest 9.0.2, Ruff 0.12.12.

**Spec:** `docs/superpowers/specs/2026-08-24-shared-content-store-artifact-ingestion-design.md`

## Global Constraints

- Preserve the existing object layout exactly: `objects/sha256/<first-two-hex>/<remaining-62-hex>`.
- Preserve `CacheReceipt` fields, receipt paths, and repeated-fetch idempotence; existing cache directories require no migration.
- `ContentStore` is the only code that publishes or verifies content-addressed object bytes.
- `ContentAddressedCache` remains the acquisition-facing API and delegates byte storage to `ContentStore`.
- Ingestion consumes `CacheReceipt` evidence only. It accepts no local source path or raw payload and never calls `ContentStore.put_bytes`.
- Reuse `sha256_bytes` and `sha256_file`; do not create another SHA-256 implementation.
- Exact bytes are the v1 artifact deduplication boundary.
- Artifact IDs are `om.puzzle-artifact.sha256.<digest>` and `om.solution.sha256.<digest>`.
- Artifact-level rights fold only artifact-receipt rights: `local_fetch_only` > `unknown` > `redistributable`.
- Every artifact candidate emits artifact-source provenance. Distinct metadata evidence emits a separate evidence-source provenance fact.
- Attached evidence must share `source_id` and `revision` with the artifact receipt.
- Source-claimed metrics remain provenance-only. Do not invent verifier state.
- Do not modify adapter semantics, release schemas, release materialization, normalization, verifier behavior, or Hugging Face publication.
- No new third-party dependencies.

---

### Task 1: Extract the authoritative exact-byte `ContentStore`

**Files:**
- Create: `src/opus_corpus/content_store.py`
- Create: `tests/test_content_store.py`
- Read only: `src/opus_corpus/hashing.py`

**Interfaces:**
- Produces: `ContentStoreError(CorpusError)`
- Produces: `StoredObject(sha256: str, byte_length: int, object_key: str)`
- Produces: `ContentStore(root: Path)`
- Produces: `ContentStore.put_bytes(payload: bytes) -> StoredObject`
- Produces: `ContentStore.require(sha256: str, byte_length: int) -> StoredObject`
- Produces: `ContentStore.object_path(sha256: str) -> Path`

- [ ] **Step 1: Write the failing layout/idempotence tests**

Create `tests/test_content_store.py`:

```python
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from opus_corpus.content_store import ContentStore, ContentStoreError


def test_put_bytes_preserves_existing_object_layout(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    payload = b"abc"
    digest = hashlib.sha256(payload).hexdigest()
    stored = store.put_bytes(payload)
    assert stored.sha256 == digest
    assert stored.byte_length == len(payload)
    assert stored.object_key == f"objects/sha256/{digest[:2]}/{digest[2:]}"
    assert store.object_path(digest) == tmp_path / stored.object_key
    assert store.object_path(digest).read_bytes() == payload


def test_put_bytes_is_idempotent_for_identical_bytes(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    assert store.put_bytes(b"same") == store.put_bytes(b"same")


def test_distinct_bytes_produce_distinct_objects(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = store.put_bytes(b"first")
    second = store.put_bytes(b"second")
    assert first.sha256 != second.sha256
    assert first.object_key != second.object_key
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run pytest tests/test_content_store.py -q
```

Expected: import/collection failure because `opus_corpus.content_store` does not exist.

- [ ] **Step 3: Implement the value type, path contract, verification, and publication**

Create `src/opus_corpus/content_store.py`:

```python
from __future__ import annotations

import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import CorpusError
from .hashing import sha256_bytes, sha256_file

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ContentStoreError(CorpusError):
    """Raised when content-addressed object storage is invalid or corrupt."""


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    byte_length: int
    object_key: str


class ContentStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    @staticmethod
    def _validate_digest(sha256: str) -> str:
        if _SHA256_RE.fullmatch(sha256) is None:
            raise ContentStoreError(f"invalid sha256 digest {sha256!r}")
        return sha256

    @staticmethod
    def _object_key(sha256: str) -> str:
        return f"objects/sha256/{sha256[:2]}/{sha256[2:]}"

    def object_path(self, sha256: str) -> Path:
        digest = self._validate_digest(sha256)
        return self.root / self._object_key(digest)

    def require(self, sha256: str, byte_length: int) -> StoredObject:
        digest = self._validate_digest(sha256)
        if byte_length < 0:
            raise ContentStoreError(f"invalid byte length {byte_length}")
        path = self.object_path(digest)
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise ContentStoreError(f"missing content object for sha256 {digest}") from exc
        except OSError as exc:
            raise ContentStoreError(f"cannot stat content object for sha256 {digest}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise ContentStoreError(f"content object for sha256 {digest} is not a regular file")
        try:
            observed_digest = sha256_file(path)
        except OSError as exc:
            raise ContentStoreError(f"cannot read content object for sha256 {digest}") from exc
        if info.st_size != byte_length:
            raise ContentStoreError(
                f"content object byte length mismatch for sha256 {digest}: "
                f"expected {byte_length}, observed {info.st_size}"
            )
        if observed_digest != digest:
            raise ContentStoreError(f"corrupt content object for sha256 {digest}")
        return StoredObject(digest, byte_length, self._object_key(digest))

    def put_bytes(self, payload: bytes) -> StoredObject:
        digest = sha256_bytes(payload)
        byte_length = len(payload)
        target = self.object_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            return self.require(digest, byte_length)

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                prefix=f".{digest}.",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_path, target)
            except FileExistsError:
                return self.require(digest, byte_length)
            return self.require(digest, byte_length)
        except ContentStoreError:
            raise
        except OSError as exc:
            raise ContentStoreError(f"cannot publish content object for sha256 {digest}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Add integrity/race/cleanup tests**

Append:

```python
def test_require_accepts_valid_existing_object(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.put_bytes(b"payload")
    assert store.require(stored.sha256, stored.byte_length) == stored


def test_require_rejects_missing_object(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"missing").hexdigest()
    with pytest.raises(ContentStoreError, match="missing content object"):
        ContentStore(tmp_path).require(digest, 7)


def test_require_rejects_corrupt_object(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    payload = b"expected"
    digest = hashlib.sha256(payload).hexdigest()
    path = store.object_path(digest)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt!")
    with pytest.raises(ContentStoreError, match="corrupt content object"):
        store.require(digest, len(payload))


def test_require_rejects_byte_length_mismatch(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.put_bytes(b"payload")
    with pytest.raises(ContentStoreError, match="byte length mismatch"):
        store.require(stored.sha256, stored.byte_length + 1)


def test_require_rejects_symlink_object(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    real = tmp_path / "real"
    real.write_bytes(payload)
    path = store.object_path(digest)
    path.parent.mkdir(parents=True)
    path.symlink_to(real)
    with pytest.raises(ContentStoreError, match="not a regular file"):
        store.require(digest, len(payload))


@pytest.mark.parametrize("digest", ["", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_invalid_digest_fails_explicitly(tmp_path: Path, digest: str) -> None:
    with pytest.raises(ContentStoreError, match="invalid sha256 digest"):
        ContentStore(tmp_path).object_path(digest)


def test_concurrent_mismatching_winner_is_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ContentStore(tmp_path)
    payload = b"expected"
    digest = hashlib.sha256(payload).hexdigest()
    target = store.object_path(digest)

    def publish_corrupt_winner(src: Path, dst: Path) -> None:
        Path(dst).write_bytes(b"corrupt")
        raise FileExistsError

    monkeypatch.setattr(os, "link", publish_corrupt_winner)
    with pytest.raises(ContentStoreError):
        store.put_bytes(payload)
    assert target.read_bytes() == b"corrupt"


def test_publication_temp_files_are_removed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.put_bytes(b"payload")
    directory = store.object_path(stored.sha256).parent
    assert [p for p in directory.iterdir() if p.name.startswith(f".{stored.sha256}.")] == []
```

- [ ] **Step 5: Verify GREEN and lint**

```bash
uv run pytest tests/test_content_store.py -q
uv run ruff check src/opus_corpus/content_store.py tests/test_content_store.py
```

Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/opus_corpus/content_store.py tests/test_content_store.py
git commit -m "refactor: extract content-addressed store"
```

---

### Task 2: Delegate acquisition cache bytes to `ContentStore`

**Files:**
- Modify: `src/opus_corpus/cache.py`
- Modify: `tests/test_cache.py`
- Regression only: `tests/test_om_archive.py`
- Regression only: `tests/test_om_leaderboard.py`

**Interfaces:**
- Consumes: `ContentStore`, `ContentStoreError`
- Preserves: `CacheIntegrityError`, `CacheReceipt`, `put_bytes`, `object_path`, `receipt_path`
- Produces: `ContentAddressedCache.store: ContentStore`

- [ ] **Step 1: Add the RED structural delegation test plus compatibility tests**

Add `hashlib`, `json`, `Path`, `CacheReceipt`, and `ContentStore` imports as needed. Append:

```python
def test_cache_exposes_shared_content_store(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    assert isinstance(cache.store, ContentStore)
    assert cache.store.root == tmp_path


def test_object_path_compatibility_preserves_existing_layout(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt = cache.put_bytes(
        "source", "rev", "path/a.solution", b"abc", rights_status="local_fetch_only"
    )
    assert cache.object_path(receipt.sha256) == (
        tmp_path / "objects" / "sha256" / receipt.sha256[:2] / receipt.sha256[2:]
    )


def test_preexisting_cache_directory_requires_no_migration(tmp_path: Path) -> None:
    payload = b"legacy-cache-payload"
    digest = hashlib.sha256(payload).hexdigest()
    object_path = tmp_path / "objects" / "sha256" / digest[:2] / digest[2:]
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(payload)
    cache = ContentAddressedCache(tmp_path)
    receipt_path = cache.receipt_path("source", "rev", "path/a.solution")
    receipt_path.parent.mkdir(parents=True)
    old_receipt = {
        "source_id": "source",
        "revision": "rev",
        "upstream_path": "path/a.solution",
        "sha256": digest,
        "byte_length": len(payload),
        "rights_status": "local_fetch_only",
        "retrieved_at": "2026-08-24T12:00:00+00:00",
    }
    receipt_path.write_text(
        json.dumps(old_receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    before = receipt_path.read_bytes()
    receipt = cache.put_bytes(
        "source", "rev", "path/a.solution", payload, rights_status="local_fetch_only"
    )
    assert receipt == CacheReceipt(**old_receipt)
    assert receipt_path.read_bytes() == before
    assert object_path.read_bytes() == payload
```

- [ ] **Step 2: Run the structural test and verify RED**

```bash
uv run pytest tests/test_cache.py::test_cache_exposes_shared_content_store -q
```

Expected: failure because current `ContentAddressedCache` has no `store` attribute.

- [ ] **Step 3: Refactor `cache.py` to delegate bytes**

Keep `CacheReceipt`, receipt-path hashing, receipt JSON serialization, and `_read_receipt` semantics unchanged. Replace direct object handling with:

```python
from .content_store import ContentStore, ContentStoreError


class ContentAddressedCache:
    """Local cache of immutable source bytes plus provenance receipts."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.store = ContentStore(self.root)

    def object_path(self, sha256: str) -> Path:
        return self.store.object_path(sha256)

    def put_bytes(
        self,
        source_id: str,
        revision: str,
        upstream_path: str,
        payload: bytes,
        *,
        rights_status: str,
    ) -> CacheReceipt:
        try:
            stored = self.store.put_bytes(payload)
        except ContentStoreError as exc:
            raise CacheIntegrityError(str(exc)) from exc

        receipt_path = self.receipt_path(source_id, revision, upstream_path)
        if receipt_path.exists():
            existing = self._read_receipt(receipt_path)
            expected = (
                source_id,
                revision,
                upstream_path,
                stored.sha256,
                stored.byte_length,
                rights_status,
            )
            observed = (
                existing.source_id,
                existing.revision,
                existing.upstream_path,
                existing.sha256,
                existing.byte_length,
                existing.rights_status,
            )
            if observed != expected:
                raise CacheIntegrityError(
                    f"pinned source path changed: {source_id}@{revision}:{upstream_path}"
                )
            return existing

        receipt = CacheReceipt(
            source_id=source_id,
            revision=revision,
            upstream_path=upstream_path,
            sha256=stored.sha256,
            byte_length=stored.byte_length,
            rights_status=rights_status,
            retrieved_at=dt.datetime.now(dt.UTC).isoformat(),
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return receipt
```

Remove only imports made obsolete by the delegation.

- [ ] **Step 4: Add public acquisition error compatibility**

Append:

```python
def test_cache_wraps_store_corruption_as_cache_integrity_error(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    payload = b"abc"
    digest = hashlib.sha256(payload).hexdigest()
    path = cache.object_path(digest)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt")
    with pytest.raises(CacheIntegrityError):
        cache.put_bytes(
            "source", "rev", "path/a.solution", payload, rights_status="local_fetch_only"
        )
    assert path.read_bytes() == b"corrupt"
```

- [ ] **Step 5: Verify GREEN, cache compatibility, and unchanged acquisition behavior**

```bash
uv run pytest tests/test_cache.py tests/test_om_archive.py tests/test_om_leaderboard.py -q
uv run ruff check src/opus_corpus/cache.py tests/test_cache.py
```

Expected: all pass without semantic edits to acquisition adapters.

- [ ] **Step 6: Commit**

```bash
git add src/opus_corpus/cache.py tests/test_cache.py
git commit -m "refactor: delegate cache objects to content store"
```

---

### Task 3: Add receipt-only artifact/provenance ingestion

**Files:**
- Create: `src/opus_corpus/ingestion.py`
- Create: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: `CacheReceipt`, `ContentStore`, `StoredObject`
- Produces: `ArtifactIngestionError(CorpusError)`
- Produces: `ObservedArtifactCandidate`
- Produces: `ArtifactRecord`
- Produces: `ArtifactProvenance`
- Produces: `IngestionResult`
- Produces: `ingest_artifacts(candidates: Iterable[ObservedArtifactCandidate], store: ContentStore) -> IngestionResult`

- [ ] **Step 1: Write the first RED tests for receipt-derived IDs**

Create `tests/test_ingestion.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.cache import CacheReceipt
from opus_corpus.content_store import ContentStore, ContentStoreError
from opus_corpus.ingestion import ArtifactIngestionError, ObservedArtifactCandidate, ingest_artifacts


def _receipt(
    store: ContentStore,
    payload: bytes,
    *,
    source_id: str = "om-archive",
    revision: str = "revision-a",
    upstream_path: str = "CHAPTER_1/P001/example.solution",
    rights_status: str = "local_fetch_only",
    retrieved_at: str = "2026-08-24T12:00:00+00:00",
) -> CacheReceipt:
    stored = store.put_bytes(payload)
    return CacheReceipt(
        source_id=source_id,
        revision=revision,
        upstream_path=upstream_path,
        sha256=stored.sha256,
        byte_length=stored.byte_length,
        rights_status=rights_status,
        retrieved_at=retrieved_at,
    )


def _candidate(receipt: CacheReceipt, **overrides: object) -> ObservedArtifactCandidate:
    values: dict[str, object] = {
        "artifact_kind": "solution",
        "puzzle_id": "om.puzzle.0001",
        "artifact_format": "solution",
        "artifact_receipt": receipt,
        "evidence_receipt": None,
        "source_object_id": None,
        "source_url": None,
        "author": "Example Author",
        "claimed_cost": 20,
        "claimed_cycles": 40,
        "claimed_area": 10,
        "claimed_instructions": 6,
    }
    values.update(overrides)
    return ObservedArtifactCandidate(**values)  # type: ignore[arg-type]


def test_solution_identity_comes_from_receipt_digest(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"solution bytes")
    result = ingest_artifacts([_candidate(receipt)], store)
    artifact = result.artifacts[0]
    assert artifact.artifact_id == f"om.solution.sha256.{receipt.sha256}"
    assert artifact.object_key == f"objects/sha256/{receipt.sha256[:2]}/{receipt.sha256[2:]}"


def test_puzzle_identity_uses_distinct_namespace(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"puzzle bytes", upstream_path="test/puzzle/P007.puzzle")
    result = ingest_artifacts(
        [_candidate(receipt, artifact_kind="puzzle", artifact_format="puzzle")], store
    )
    assert result.artifacts[0].artifact_id == f"om.puzzle-artifact.sha256.{receipt.sha256}"
```

- [ ] **Step 2: Run the first focused tests and verify RED**

```bash
uv run pytest tests/test_ingestion.py -q
```

Expected: import/collection failure because `opus_corpus.ingestion` does not exist.

- [ ] **Step 3: Implement contracts, validation, and the minimal one-candidate path**

Create `src/opus_corpus/ingestion.py` with the data contracts and helpers below. The temporary `ingest_artifacts` implementation intentionally does no deduplication yet; Step 6 replaces it after the next RED tests.

```python
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


def _validate_candidate(candidate: ObservedArtifactCandidate, store: ContentStore) -> _IngestedCandidate:
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
```

- [ ] **Step 4: Verify the first cycle is GREEN**

```bash
uv run pytest tests/test_ingestion.py::test_solution_identity_comes_from_receipt_digest \
  tests/test_ingestion.py::test_puzzle_identity_uses_distinct_namespace -q
```

Expected: both pass.

- [ ] **Step 5: Add RED tests for provenance, deduplication, evidence, rights, ordering, and conflicts**

Append:

```python
def test_identical_bytes_deduplicate_without_losing_provenance(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"same", source_id="a", upstream_path="a.solution")
    second = _receipt(store, b"same", source_id="b", upstream_path="b.solution")
    result = ingest_artifacts([_candidate(first), _candidate(second, claimed_cost=19)], store)
    assert len(result.artifacts) == 1
    assert len(result.provenance) == 2
    assert {row.source_id for row in result.provenance} == {"a", "b"}
    assert not hasattr(result.artifacts[0], "claimed_cost")


def test_exact_duplicate_provenance_collapses(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"same")
    candidate = _candidate(receipt)
    result = ingest_artifacts([candidate, candidate], store)
    assert len(result.artifacts) == 1
    assert len(result.provenance) == 1


def test_distinct_bytes_never_deduplicate(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"first", upstream_path="first.solution")
    second = _receipt(store, b"second", upstream_path="second.solution")
    assert len(ingest_artifacts([_candidate(first), _candidate(second)], store).artifacts) == 2


def test_distinct_metadata_evidence_emits_second_provenance_fact(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(
        store, b"solution", source_id="om-leaderboard", upstream_path="P/a.solution"
    )
    evidence = _receipt(
        store, b'{"cost":19}', source_id="om-leaderboard", upstream_path="P/a.json"
    )
    result = ingest_artifacts(
        [_candidate(artifact, evidence_receipt=evidence, claimed_cost=19)], store
    )
    assert len(result.provenance) == 2
    artifact_row = next(row for row in result.provenance if row.source_role == "artifact")
    evidence_row = next(row for row in result.provenance if row.source_role == "evidence")
    assert artifact_row.source_path.endswith("a.solution")
    assert artifact_row.claimed_cost is None
    assert evidence_row.source_path.endswith("a.json")
    assert evidence_row.claimed_cost == 19
    assert evidence_row.observed_sha256 == artifact.sha256
    assert evidence_row.source_evidence_sha256 == evidence.sha256


def test_same_receipt_as_evidence_emits_one_provenance_fact(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"solution")
    result = ingest_artifacts([_candidate(receipt, claimed_cost=20)], store)
    assert len(result.provenance) == 1
    assert result.provenance[0].source_role == "artifact"
    assert result.provenance[0].claimed_cost == 20


def test_artifact_rights_ignore_more_restrictive_metadata_rights(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"same", rights_status="redistributable")
    evidence = _receipt(
        store, b"meta", upstream_path="a.json", rights_status="local_fetch_only"
    )
    result = ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)
    assert result.artifacts[0].rights_status == "redistributable"
    assert {row.rights_status for row in result.provenance} == {
        "redistributable",
        "local_fetch_only",
    }


def test_artifact_rights_fold_is_conservative(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipts = [
        _receipt(store, b"same", source_id="a", upstream_path="a", rights_status="redistributable"),
        _receipt(store, b"same", source_id="b", upstream_path="b", rights_status="unknown"),
        _receipt(store, b"same", source_id="c", upstream_path="c", rights_status="local_fetch_only"),
    ]
    result = ingest_artifacts([_candidate(receipt) for receipt in receipts], store)
    assert result.artifacts[0].rights_status == "local_fetch_only"


def test_invalid_evidence_rights_fail_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"artifact")
    evidence = _receipt(store, b"meta", upstream_path="a.json", rights_status="invented")
    with pytest.raises(ArtifactIngestionError, match="invalid rights status"):
        ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)


def test_candidate_order_and_cache_root_do_not_change_output(tmp_path: Path) -> None:
    left = ContentStore(tmp_path / "left")
    right = ContentStore(tmp_path / "right")
    left_a = _receipt(left, b"alpha", source_id="a", upstream_path="stable/a")
    left_b = _receipt(left, b"beta", source_id="b", upstream_path="stable/b")
    right_a = _receipt(right, b"alpha", source_id="a", upstream_path="stable/a")
    right_b = _receipt(right, b"beta", source_id="b", upstream_path="stable/b")
    assert ingest_artifacts([_candidate(left_b), _candidate(left_a)], left) == ingest_artifacts(
        [_candidate(right_a), _candidate(right_b)], right
    )


def test_same_digest_for_different_puzzles_fails_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"same", source_id="a", upstream_path="a")
    second = _receipt(store, b"same", source_id="b", upstream_path="b")
    with pytest.raises(ArtifactIngestionError, match="different puzzle IDs"):
        ingest_artifacts(
            [_candidate(first), _candidate(second, puzzle_id="om.puzzle.0002")], store
        )


def test_conflicting_formats_fail_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"same", source_id="a", upstream_path="a")
    second = _receipt(store, b"same", source_id="b", upstream_path="b")
    with pytest.raises(ArtifactIngestionError, match="conflicting artifact formats"):
        ingest_artifacts(
            [_candidate(first), _candidate(second, artifact_format="legacy-solution")], store
        )


def test_same_artifact_receipt_identity_cannot_change_association(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"same")
    with pytest.raises(ArtifactIngestionError, match="artifact receipt identity has conflicting"):
        ingest_artifacts(
            [_candidate(receipt), _candidate(receipt, puzzle_id="om.puzzle.0002")], store
        )


def test_evidence_assertion_identity_cannot_support_two_artifacts(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"first", upstream_path="first.solution")
    second = _receipt(store, b"second", upstream_path="second.solution")
    evidence = _receipt(store, b"meta", upstream_path="scores.json")
    with pytest.raises(ArtifactIngestionError, match="supports multiple artifacts"):
        ingest_artifacts(
            [
                _candidate(first, evidence_receipt=evidence, source_object_id="row-1"),
                _candidate(second, evidence_receipt=evidence, source_object_id="row-1"),
            ],
            store,
        )


def test_cross_source_attached_evidence_fails_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"artifact", source_id="a")
    evidence = _receipt(store, b"meta", source_id="b", upstream_path="meta.json")
    with pytest.raises(ArtifactIngestionError, match="share artifact source and revision"):
        ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)


def test_puzzle_and_solution_namespaces_share_object_not_identity(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    puzzle_receipt = _receipt(store, b"identical", upstream_path="puzzle/P007.puzzle")
    solution_receipt = _receipt(store, b"identical", upstream_path="solution/P007.solution")
    result = ingest_artifacts(
        [
            _candidate(puzzle_receipt, artifact_kind="puzzle", artifact_format="puzzle"),
            _candidate(solution_receipt),
        ],
        store,
    )
    by_kind = {row.artifact_kind: row for row in result.artifacts}
    assert by_kind["puzzle"].artifact_id != by_kind["solution"].artifact_id
    assert by_kind["puzzle"].sha256 == by_kind["solution"].sha256
    assert by_kind["puzzle"].object_key == by_kind["solution"].object_key


def test_missing_object_propagates_content_store_error(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"artifact")
    store.object_path(receipt.sha256).unlink()
    with pytest.raises(ContentStoreError, match="missing content object"):
        ingest_artifacts([_candidate(receipt)], store)
```

- [ ] **Step 6: Run the new tests and verify RED against the minimal path**

```bash
uv run pytest tests/test_ingestion.py -q
```

Expected: stable-ID tests pass; provenance/deduplication/order/conflict tests fail because the temporary implementation returns linear artifacts and no provenance.

- [ ] **Step 7: Replace the minimal path with provenance emission, grouping, rights folding, and identity checks**

Add these helpers and replace `ingest_artifacts`:

```python
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


def _provenance_sort_key(row: ArtifactProvenance) -> tuple[str, ...]:
    return tuple(
        "" if value is None else str(value)
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
```

- [ ] **Step 8: Verify GREEN and lint**

```bash
uv run pytest tests/test_ingestion.py -q
uv run ruff check src/opus_corpus/ingestion.py tests/test_ingestion.py
```

Expected: all ingestion tests and lint pass.

- [ ] **Step 9: Commit**

```bash
git add src/opus_corpus/ingestion.py tests/test_ingestion.py
git commit -m "feat: ingest artifacts from cache receipts"
```

---

### Task 4: Repository acceptance and draft PR

**Files:**
- Modify only for a concrete test-driven defect: the three production modules and their tests
- No planned adapter, schema, release, CLI, fixture, or publication changes

**Interfaces:**
- Consumes: completed `ContentStore`, cache delegation, and receipt-based ingestion
- Produces: a `main`-based review branch with one authoritative exact-byte storage path

- [ ] **Step 1: Run focused tests together**

```bash
uv run pytest tests/test_content_store.py tests/test_cache.py tests/test_ingestion.py -v
```

Expected: all storage, compatibility, provenance, deduplication, evidence, rights, conflict, and corruption cases pass.

- [ ] **Step 2: Run landed acquisition regressions unchanged**

```bash
uv run pytest tests/test_om_archive.py tests/test_om_leaderboard.py -q
```

Expected: exit 0 without adapter semantic changes.

- [ ] **Step 3: Run repository lint and full tests**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: both exit 0.

- [ ] **Step 4: Validate frozen collection and tiny release path**

```bash
uv run opus-corpus collections validate
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

Expected: every command exits 0.

- [ ] **Step 5: Verify scope and one-authoritative-path invariant**

```bash
git diff main...HEAD --name-only
rg 'objects/sha256|os\.link|NamedTemporaryFile|write_bytes\(payload\)' src/opus_corpus
```

Expected changed production paths are limited to `content_store.py`, `cache.py`, and `ingestion.py`; storage publication primitives appear only in `content_store.py`; `cache.py` delegates; `ingestion.py` contains neither an object-layout constructor nor a byte publication call.

- [ ] **Step 6: Commit only a concrete acceptance correction if required**

For any failure in Steps 1-5, add a failing regression test first, fix the smallest defect, rerun the relevant focused command, then rerun Steps 3-5. Commit only actual corrections:

```bash
git add src/opus_corpus/content_store.py src/opus_corpus/cache.py src/opus_corpus/ingestion.py \
  tests/test_content_store.py tests/test_cache.py tests/test_ingestion.py
git commit -m "fix: satisfy shared store ingestion acceptance"
```

If no correction is required, create no empty commit.

- [ ] **Step 7: Open a draft PR directly against `main`**

Use exactly:

```text
base: main
head: feature/shared-content-store-ingestion
draft: true
title: Share content store with artifact ingestion
```

Use this body:

```markdown
Creates one authoritative exact-byte storage boundary and builds receipt-based artifact ingestion on top of it.

- Extracts the existing SHA-256 object layout and integrity checks into `ContentStore` without migrating cache data.
- Keeps `ContentAddressedCache` acquisition semantics and receipt identity stable while delegating object storage.
- Adds deterministic puzzle/solution artifact identities and exact-byte deduplication from persisted `CacheReceipt` evidence.
- Preserves artifact-byte provenance separately from metadata evidence such as adjacent om-leaderboard JSON claims.
- Folds artifact rights conservatively from artifact receipts while leaving source claims provenance-only.
- Fails closed on ambiguous puzzle/format associations, contradictory receipt/evidence identities, invalid rights, and missing/corrupt cached objects.
- Keeps adapters, verifier execution, normalization, release schemas, and release materialization out of scope.

Validation: repository lint, full tests, frozen collection validation, and tiny release build/validate/stage pass.
```

Do not merge the PR as part of this plan.
