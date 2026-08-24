# Collection schema and validator design

Status: **semantic contract retained; standalone toolchain decision superseded**
Date: 2026-08-23

## Supersession

The collection semantics in this document remain authoritative design input, but the originally proposed standalone Python-standard-library validator toolchain is no longer the implementation path.

`docs/superpowers/specs/2026-08-23-hugging-face-template-adoption-design.md` establishes one repository toolchain instead: the `opus_corpus` package uses Python 3.12, Draft 2020-12 JSON Schema execution, the shared typed error model, pytest, and the same CLI as release construction and validation. This removes a parallel validator framework without changing collection authority or validation semantics.

Collection authority remains the checked-in `collections/*.toml` manifest plus its referenced CSV inventory. Validation derives facts from those files and never writes a generated catalog, count ledger, or secondary index.

## Goal

Reject drift between a frozen collection manifest and its inventory before any source adapter or corpus build consumes the collection.

The validator does not acquire source payloads, validate puzzle bytes, run `omsim`, or define solution semantics. It validates collection identity and membership only.

## Machine-readable contracts

The repository owns two JSON Schema 2020-12 documents:

- `schemas/collection-manifest.schema.json`
- `schemas/collection-inventory-row.schema.json`

The manifest requires schema version `1`, an immutable slug collection ID, ISO effective date, frozen status, puzzle count, basename CSV inventory reference, SHA-256 inventory hash, scope/exclusions, membership-source evidence, release evidence, and non-negative group-count rollups.

The inventory header is exact and ordered:

```text
puzzle_id,display_name,kind,group,game_puzzle_id,leaderboard_key,puzzle_type
```

Rows require stable `om.puzzle.NNNN` IDs, non-empty display names, declared puzzle kinds, lowercase slug groups, game IDs matching `P` plus three digits and optional lowercase suffix, uppercase leaderboard keys, and one supported puzzle type.

## Group-count rollup semantics

Manifest rollups may summarize finer inventory groups. A `group_counts` key is converted to a group prefix by replacing `_` with `-`.

A row belongs to a rollup when its `group` equals that prefix or starts with `prefix + "-"`. For example:

- `chapter_1` matches `chapter-1`;
- `appendix` matches `appendix`;
- `journal_xcix` matches `journal-xcix-i` through `journal-xcix-xii`.

Every row must match exactly one declared rollup. Zero matches are rejected as stale/incomplete summary state; multiple matches are rejected as overlapping declarations. Observed rollup counts must equal the manifest values.

## Semantic validation

For each collection manifest, the unified validator:

1. parses TOML and executes the collection-manifest JSON Schema;
2. requires `inventory_file` to be a basename resolved only within the manifest directory;
3. verifies the raw inventory SHA-256 before semantic use;
4. decodes UTF-8 and requires the exact ordered CSV header;
5. executes the inventory-row JSON Schema for every row;
6. rejects duplicate canonical puzzle IDs, game puzzle IDs, or leaderboard keys;
7. requires ordered contiguous puzzle IDs from `om.puzzle.0001` through `om.puzzle.NNNN`;
8. requires inventory row count to equal `puzzle_count`;
9. assigns every row to exactly one declared group rollup;
10. requires every observed group rollup count to equal the manifest;
11. reports deterministic structured errors and never repairs authoritative files automatically.

## Error model and CLI

Collection errors use the shared repository `ValidationError` structure with a stable code, path, optional row number, and human-readable detail. Important codes include:

- `manifest_parse_error`
- `manifest_schema_error`
- `inventory_path_error`
- `inventory_missing`
- `inventory_hash_mismatch`
- `inventory_decode_error`
- `inventory_header_error`
- `inventory_row_error`
- `duplicate_puzzle_id`
- `duplicate_game_puzzle_id`
- `duplicate_leaderboard_key`
- `puzzle_id_sequence_error`
- `puzzle_count_mismatch`
- `group_rollup_unmatched`
- `group_rollup_overlap`
- `group_counts_mismatch`

The implemented CLI surface is:

```text
opus-corpus collections validate [manifest]
```

With no manifest it validates every checked-in collection in lexical order. Success exits `0`, collection/data validation failure exits `1`, and configuration/operational misuse exits `2`.

## Testing requirements

Tests retain the original corruption matrix:

1. the committed `base-game-2026-06-16` manifest and 166-row inventory validate;
2. SHA-256 drift is rejected;
3. row-count mismatch is rejected;
4. duplicate canonical puzzle ID is rejected;
5. duplicate upstream game puzzle ID is rejected;
6. duplicate leaderboard key is rejected;
7. non-contiguous/out-of-order canonical IDs are rejected;
8. malformed game IDs, groups, and puzzle types are rejected;
9. exact CSV header/order is enforced;
10. group-count rollups are checked against finer row groups;
11. unmatched and overlapping rollups are rejected;
12. inventory path traversal is rejected;
13. malformed TOML fails cleanly;
14. repeated validation produces deterministic ordered errors.

Synthetic fixtures exercise corruption cases without modifying the frozen collection. CI additionally validates the committed collection itself.

## Authority boundary

The validator creates no second catalog. The checked-in manifest and inventory remain the only collection membership authority. Counts, hashes, rollup observations, and validation output are derived at runtime and are not committed as maintained projections.
