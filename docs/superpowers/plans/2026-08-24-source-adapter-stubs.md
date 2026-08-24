# Source Adapter Stubs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a test-backed source-adapter contract, registry, and six explicit unimplemented adapters for the currently identified Opus Magnum source classes.

**Architecture:** Add a focused `opus_corpus.adapters` package. A small `SourceAdapter` base class owns source metadata and the fail-closed default `fetch` behavior; source modules only declare metadata. A registry is the single deterministic lookup surface.

**Tech Stack:** Python 3.12, dataclasses, pathlib, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-24-source-adapter-stubs-design.md`

## Global Constraints

- Do not implement network acquisition, content-addressed caching, parsing, verification, normalization, or release wiring in this slice.
- Do not add dependencies.
- Keep pinned revisions identical to `docs/source-inventory.md`.
- The official-game adapter has no source repository revision; future local artifact hashes provide immutable identity.
- Unimplemented acquisition must fail closed with a typed error.

---

### Task 1: Lock the adapter contract with failing tests

**Files:**
- Create: `tests/test_adapters.py`

**Interfaces:**
- Consumes: `CollectionDefinition` from `opus_corpus.collections`.
- Produces expectations for `SourceAdapter`, `AdapterNotImplementedError`, `ADAPTERS`, and six adapter classes.

- [ ] **Step 1: Write the failing contract test**

Create tests that import the adapter package, assert the exact six registry keys and pinned revisions, assert each class derives from `SourceAdapter`, and call `fetch` with a minimal `CollectionDefinition` plus a temporary cache path expecting `AdapterNotImplementedError` containing the source ID.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adapters.py -q`
Expected: FAIL during import because `opus_corpus.adapters` does not exist.

- [ ] **Step 3: Commit the red test**

Commit message: `test: define source adapter contract`

### Task 2: Implement the minimal base contract and source stubs

**Files:**
- Create: `src/opus_corpus/adapters/__init__.py`
- Create: `src/opus_corpus/adapters/base.py`
- Create: `src/opus_corpus/adapters/leaderboard_bot.py`
- Create: `src/opus_corpus/adapters/om_archive.py`
- Create: `src/opus_corpus/adapters/om_leaderboard.py`
- Create: `src/opus_corpus/adapters/omsim.py`
- Create: `src/opus_corpus/adapters/molecule_db.py`
- Create: `src/opus_corpus/adapters/official_game.py`

**Interfaces:**
- Produces: `class AdapterNotImplementedError(RuntimeError)`.
- Produces: `@dataclass(frozen=True) class SourceAdapter` with class metadata `source_id` and `pinned_revision`, plus `fetch(self, collection: CollectionDefinition, cache_root: Path) -> None`.
- Produces: one subclass per source and `ADAPTERS: dict[str, type[SourceAdapter]]`.

- [ ] **Step 1: Write the base class**

The base `fetch` method raises `AdapterNotImplementedError(f"source adapter {self.source_id!r} is not implemented")`.

- [ ] **Step 2: Add six metadata-only subclasses**

Use these stable source IDs and revisions:

```text
leaderboard-bot ca40dee95da584270eb3be1c4b74e2be63afa7e6
om-archive 44006a0eeb0051337640443d1b0576ea24c983f6
om-leaderboard 0cfd371ef66cf94eac3f7a7a06bc9ab959495576
omsim 758f4a4b4c9e24f50294801da774a0960c922bab
molecule-db 6f3cd8068428ef96ac6426d092c3523da359ec76
official-game <None>
```

- [ ] **Step 3: Add the deterministic registry and package exports**

`ADAPTERS` maps the six source IDs to their classes. Export the base type, error, registry, and classes from `opus_corpus.adapters`.

- [ ] **Step 4: Run the focused tests**

Run: `uv run pytest tests/test_adapters.py -q`
Expected: PASS.

- [ ] **Step 5: Run repository verification**

Run:

```bash
uv run ruff check .
uv run pytest -q
uv run opus-corpus collections validate
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit implementation**

Commit message: `feat: stub source adapters`
