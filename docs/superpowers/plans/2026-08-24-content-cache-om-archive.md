# Content Cache and om-archive Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content-addressed acquisition cache and make the pinned `om-archive` adapter fetch matching solution bytes for a frozen collection.

**Architecture:** Keep acquisition separate from canonical build state. `cache.py` owns byte identity and receipts, `github_source.py` owns pinned GitHub tarball transport, and `om_archive.py` owns source-specific path mapping. The CLI invokes one explicitly selected adapter.

**Tech Stack:** Python 3.12 standard library, pytest 9.0.2, ruff 0.12.12.

**Spec:** `docs/superpowers/specs/2026-08-24-content-cache-om-archive-design.md`

## Global Constraints

- Network acquisition and deterministic materialization remain separate operations.
- The frozen collection inventory remains puzzle-membership authority.
- Raw `om-archive` solution bytes are `local_fetch_only`.
- No source-declared score embedded in a filename becomes verified metrics.
- Tests must not require network access.

---

### Task 1: Content-addressed cache

**Files:**
- Create: `src/opus_corpus/cache.py`
- Create: `tests/test_cache.py`

**Interfaces:**
- Produces: `CacheReceipt`, `CacheIntegrityError`, `ContentAddressedCache.put_bytes(...)`.

- [ ] **Step 1: Write failing cache tests**

```python
from opus_corpus.cache import CacheIntegrityError, ContentAddressedCache


def test_put_bytes_is_content_addressed_and_idempotent(tmp_path):
    cache = ContentAddressedCache(tmp_path)
    first = cache.put_bytes("source", "rev", "a.solution", b"abc", "local_fetch_only")
    second = cache.put_bytes("source", "rev", "a.solution", b"abc", "local_fetch_only")
    assert first == second
    assert cache.object_path(first.sha256).read_bytes() == b"abc"


def test_put_bytes_rejects_changed_payload_for_pinned_path(tmp_path):
    cache = ContentAddressedCache(tmp_path)
    cache.put_bytes("source", "rev", "a.solution", b"abc", "local_fetch_only")
    with pytest.raises(CacheIntegrityError):
        cache.put_bytes("source", "rev", "a.solution", b"xyz", "local_fetch_only")
```

- [ ] **Step 2: Run cache tests and verify RED**

Run: `uv run pytest -q tests/test_cache.py`
Expected: collection error because `opus_corpus.cache` does not exist.

- [ ] **Step 3: Implement minimal cache**

Implement `CacheReceipt` as a frozen dataclass. Store objects beneath `objects/sha256/<first-two>/<remainder>` and receipts beneath `receipts/<source>/<revision>/<receipt-key>.json`. Existing receipts must be reused only when all immutable fields match.

- [ ] **Step 4: Run cache tests and verify GREEN**

Run: `uv run pytest -q tests/test_cache.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/opus_corpus/cache.py tests/test_cache.py
git commit -m "feat: add content-addressed acquisition cache"
```

---

### Task 2: om-archive acquisition

**Files:**
- Create: `src/opus_corpus/github_source.py`
- Modify: `src/opus_corpus/adapters/base.py`
- Modify: `src/opus_corpus/adapters/om_archive.py`
- Create: `tests/test_om_archive.py`

**Interfaces:**
- Produces: `AcquisitionResult(source_id: str, candidate_count: int, puzzles_covered: int)`.
- Produces: `download_github_tarball(owner, repo, revision) -> bytes` and `tarball_files(payload, suffix) -> dict[str, bytes]`.
- `OmArchiveAdapter.fetch(collection, cache_root) -> AcquisitionResult`.

- [ ] **Step 1: Write failing acquisition tests**

Use a synthetic `CollectionDefinition` with `chapter-1/STABILIZED_WATER` and one unsupported puzzle. Build a tiny in-memory tarball containing two Stabilized Water `.solution` files plus irrelevant files. Patch `download_github_tarball` to return those bytes. Assert `candidate_count == 2`, `puzzles_covered == 1`, and two receipts exist.

- [ ] **Step 2: Run acquisition tests and verify RED**

Run: `uv run pytest -q tests/test_om_archive.py`
Expected: failure because acquisition helpers/result type are absent.

- [ ] **Step 3: Implement pinned tarball transport**

Use `urllib.request.urlopen` against `https://api.github.com/repos/{owner}/{repo}/tarball/{revision}` with a fixed user agent. Convert HTTP/network errors into a `CorpusError` subtype. Parse the returned gzip tarball entirely in-memory and return regular matching files with the generated root directory stripped.

- [ ] **Step 4: Implement manifest-to-source mapping and fetch**

Map supported collection groups explicitly. Select `.solution` members whose path begins with `<UPSTREAM_GROUP>/<leaderboard_key>/`. Store each payload through `ContentAddressedCache.put_bytes(..., rights_status="local_fetch_only")`. Return counts derived from selected files and puzzle IDs.

- [ ] **Step 5: Run acquisition tests and verify GREEN**

Run: `uv run pytest -q tests/test_om_archive.py tests/test_cache.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/opus_corpus/github_source.py src/opus_corpus/adapters/base.py src/opus_corpus/adapters/om_archive.py tests/test_om_archive.py
git commit -m "feat: acquire om-archive solution candidates"
```

---

### Task 3: Fetch CLI

**Files:**
- Modify: `src/opus_corpus/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces command: `opus-corpus fetch <collection> --source <source-id> --cache <path>`.

- [ ] **Step 1: Write failing CLI test**

Patch the registry's `om-archive` adapter `fetch` method to return `AcquisitionResult("om-archive", 2, 1)`. Invoke `main(["--config", ..., "fetch", "fixture-...", "--source", "om-archive", "--cache", ...])` and assert exit code zero plus output containing `2 candidates` and `1 puzzles`.

- [ ] **Step 2: Run CLI test and verify RED**

Run: `uv run pytest -q tests/test_cli.py`
Expected: argparse rejects the unknown `fetch` command.

- [ ] **Step 3: Implement CLI command**

Add `fetch`, required `collection`, `--source` restricted to `ADAPTERS`, and `--cache` defaulting to `.cache`. Resolve the collection through existing configuration, invoke exactly the selected adapter, and print the typed acquisition result.

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run ruff check .
uv run pytest -q
uv run opus-corpus collections validate
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add src/opus_corpus/cli.py tests/test_cli.py
git commit -m "feat: add explicit source fetch command"
```
