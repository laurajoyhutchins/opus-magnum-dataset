# Content Cache and om-archive Acquisition Design

## Goal

Make the first source adapter perform real deterministic acquisition without coupling acquisition to verification, normalization, or release generation.

This slice adds a local content-addressed cache and implements acquisition for the pinned `F43nd1r/om-archive` revision. A CLI entry point invokes that one source explicitly.

## Boundaries

This slice does:

- download the pinned `om-archive` repository snapshot;
- enumerate `.solution` files in-memory without extracting the archive;
- map source paths to the frozen collection inventory;
- store matching raw solution bytes by SHA-256;
- write stable per-source-path provenance receipts;
- report typed acquisition counts;
- expose `opus-corpus fetch <collection> --source om-archive --cache <path>`.

This slice does not:

- parse solution payloads;
- trust metrics encoded in filenames;
- verify solutions with `omsim`;
- create canonical `SolutionArtifact` or `Observation` rows;
- fetch official puzzle bytes;
- implement any other source adapter;
- publish cache contents.

## Cache layout

The cache is local generated state and is never repository authority.

```text
<cache-root>/
  objects/sha256/ab/cdef...
  receipts/<source-id>/<revision>/<receipt-key>.json
```

Object paths are derived only from the SHA-256 of their bytes. `receipt-key` is the SHA-256 of `source_id + NUL + revision + NUL + upstream_path`.

A receipt records:

- `source_id`;
- `revision`;
- `upstream_path`;
- `sha256`;
- `byte_length`;
- `rights_status`;
- `retrieved_at`.

A repeated acquisition of the same source path and same bytes reuses the existing receipt unchanged. The same source path resolving to different bytes at the same pinned revision is an integrity error and fails closed.

## om-archive transport

Acquisition downloads the GitHub tarball for the exact pinned commit. The tarball is transport only. Canonical cache identity is computed from each matching `.solution` payload, not from the generated tarball bytes.

The tarball is read with Python's `tarfile` module in-memory. No archive member is extracted to disk, avoiding path traversal concerns.

## Collection mapping

The frozen collection manifest remains the puzzle-membership authority.

For each inventory row, the adapter derives an expected upstream directory from:

- collection `group` -> `om-archive` group directory;
- `leaderboard_key` -> puzzle directory.

Supported group mappings are explicit, for example `chapter-1 -> CHAPTER_1`, `appendix -> CHAPTER_PRODUCTION`, and `journal-xcix-i -> JOURNAL_I` through `journal-xcix-ix -> JOURNAL_IX`.

The adapter then selects all regular `.solution` files under those expected directories. It never hard-codes expected puzzle or solution counts.

This matters because direct inspection of the pinned source shows `CHAPTER_1/STABILIZED_WATER` contains solution files even though the current source inventory document says P007 is absent. Source-derived coverage must therefore win over prose coverage claims.

## Result type

`SourceAdapter.fetch()` returns an `AcquisitionResult` containing:

- `source_id`;
- `candidate_count`;
- `puzzles_covered`.

Unimplemented adapters continue to raise `AdapterNotImplementedError`.

## CLI

The first CLI surface is intentionally explicit:

```text
opus-corpus fetch base-game-2026-06-16 --source om-archive --cache .cache
```

Only registered sources may be selected. Selecting an unimplemented adapter fails through its typed adapter error rather than silently skipping it.

## Testing

Tests use synthetic tarballs and temporary directories. They never depend on live network access.

The test suite must prove:

1. cache objects are content-addressed and idempotent;
2. conflicting bytes for one pinned source path fail closed;
3. tarball member normalization is deterministic;
4. manifest rows map only to matching `.solution` files;
5. `om-archive` acquisition stores bytes and returns correct counts;
6. the CLI invokes the selected adapter and reports the typed result.
