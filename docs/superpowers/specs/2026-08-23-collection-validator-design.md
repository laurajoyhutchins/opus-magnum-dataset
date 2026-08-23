# Collection schema and validator design

Status: proposed for implementation
Date: 2026-08-23

## Goal

Encode the frozen collection contract as machine-readable schemas and add one deterministic validator that rejects drift between a collection manifest and its inventory before any source adapter or corpus build is allowed to consume it.

This is the repository's first executable tooling. It must stay narrow: validate collection definitions only. It does not acquire sources, validate puzzle bytes, run `omsim`, materialize datasets, or publish artifacts.

## Context

The repository already defines collections as immutable explicit puzzle sets and requires schema/identity tests and collection-membership validation. The frozen `base-game-2026-06-16` collection now provides the first concrete manifest and inventory to validate.

The repository currently has no implementation toolchain. Introducing the validator therefore also selects the minimum initial toolchain.

## Approaches considered

### 1. Python standard library plus repository-owned schema files — selected

Use Python 3.11+ for TOML parsing (`tomllib`), CSV parsing, hashing, and CLI behavior. Store JSON Schema 2020-12 documents under `schemas/` as portable machine-readable contracts. Implement the semantic checks that JSON Schema cannot express in a small validator module.

Benefits:

- no runtime dependency is required for the first tool;
- TOML parsing is available in the standard library;
- the same language is a natural fit for later dataset/Parquet tooling;
- schema files remain language-independent;
- validation logic stays deterministic and easy to test.

Trade-off: full JSON Schema evaluation is not performed by the first validator unless a schema library is added later. The schema documents are contracts; the validator implements the same required structural rules directly.

### 2. Python plus `jsonschema`/Pydantic

This gives richer schema execution and error formatting immediately, but introduces dependency/package management before the repository needs it. It also risks making Python model classes a second schema authority.

Rejected for the first slice. A schema engine can be added when canonical entity schemas become large enough to justify it.

### 3. Rust or another compiled validator

This would provide a single binary and strong types, but introduces substantially more project machinery for a small metadata-validation problem and is not aligned with the likely later dataset/export stack.

Rejected.

## Toolchain

- Python: 3.11 or newer.
- Runtime dependencies: none.
- Test framework: `unittest` from the standard library.
- Entry point: `python -m tools.validate_collections`.
- Schemas: JSON Schema draft 2020-12 documents under `schemas/`.

No package build, lockfile, virtual-environment manager, CLI framework, or third-party validation library is introduced in this slice.

## Repository layout

```text
schemas/
  collection-manifest.schema.json
  collection-inventory-row.schema.json

tools/
  __init__.py
  validate_collections.py

tests/
  __init__.py
  test_validate_collections.py

docs/superpowers/specs/
  2026-08-23-collection-validator-design.md
```

The frozen collection files remain in `collections/` unchanged unless validation reveals a real defect.

## Machine-readable contracts

### Collection manifest schema

The manifest schema describes the current TOML manifest after parsing to a mapping. Required top-level fields:

- `schema_version`: integer, exactly `1` for this schema;
- `collection_id`: lowercase slug matching `^[a-z0-9]+(?:-[a-z0-9]+)*$`;
- `title`: non-empty string;
- `effective_date`: ISO `YYYY-MM-DD` string;
- `status`: currently `frozen`;
- `puzzle_count`: positive integer;
- `inventory_file`: basename ending in `.csv`;
- `inventory_sha256`: 64 lowercase hexadecimal characters;
- `scope`: non-empty string;
- `excludes`: array of unique non-empty strings;
- `membership_source`: object containing `source`, `revision`, `puzzle_model`, `group_model`, and `collection_model`;
- `release_evidence`: object containing `journal_final_issue_date`, `journal_issue_count`, and `source_url`;
- `group_counts`: object whose keys match `^[a-z][a-z0-9_]*$` and whose values are non-negative integers.

Unknown top-level fields are rejected in v1 so accidental manifest drift is visible. Unknown keys inside source/evidence objects are also rejected. `group_counts` keys are intentionally collection-specific rollup labels rather than alternate puzzle identities.

### Inventory row schema

The inventory CSV header is exact and ordered:

```text
puzzle_id,display_name,kind,group,game_puzzle_id,leaderboard_key,puzzle_type
```

Each row requires:

- `puzzle_id`: `om.puzzle.` followed by exactly four decimal digits;
- `display_name`: non-empty string;
- `kind`: one of `campaign`, `production`, `journal`, `expansion`, `custom`, `tournament`;
- `group`: lowercase slug matching `^[a-z0-9]+(?:-[a-z0-9]+)*$`;
- `game_puzzle_id`: `P` followed by three digits with an optional lowercase suffix;
- `leaderboard_key`: uppercase identifier using `A-Z`, digits, and underscores;
- `puzzle_type`: one of `normal`, `production`, `polymer_height`, `polymer_width`, `polymer_skew`.

The row schema describes record shape. Cross-row uniqueness and ordering are semantic validator rules.

## Group-count rollup semantics

The existing manifest intentionally summarizes some finer inventory groups. For example, `journal_xcix = 59` covers inventory groups `journal-xcix-i` through `journal-xcix-xii`. The validator must preserve that model rather than rewriting the frozen manifest to mirror row-level grouping.

For validation, each `group_counts` key is converted to a group prefix by replacing `_` with `-`.

A row belongs to a rollup when its `group` is either exactly that prefix or begins with `prefix + "-"`.

Examples:

- `chapter_1` matches `chapter-1`;
- `appendix` matches `appendix`;
- `journal_xcix` matches `journal-xcix-i` through `journal-xcix-xii`.

Every inventory row must match exactly one declared rollup. Zero matches indicate a stale/incomplete manifest summary; multiple matches indicate overlapping rollup declarations and are rejected. The observed count for each rollup must equal its manifest value.

This is deterministic derivation from authoritative row facts and does not create a second catalog.

## Semantic validation

For each `collections/*.toml` manifest, the validator:

1. parses TOML and validates its required structure and primitive types;
2. requires `inventory_file` to be a basename and resolves it only inside the manifest directory;
3. reads the inventory as raw bytes and verifies `inventory_sha256` before parsing rows;
4. decodes the inventory as UTF-8 and requires the exact ordered CSV header;
5. validates every row shape and allowed value;
6. rejects duplicate `puzzle_id`, `game_puzzle_id`, or `leaderboard_key` values;
7. requires puzzle IDs to be contiguous and ordered from `om.puzzle.0001` through `om.puzzle.NNNN` with no gaps;
8. requires the number of rows to equal `puzzle_count`;
9. assigns every row to exactly one `group_counts` rollup using the prefix rule above;
10. requires every observed rollup count to equal its manifest value;
11. reports all deterministic validation errors found for a collection in one run, then exits non-zero if any collection is invalid.

The validator never edits manifests or inventories. Repair remains an explicit repository change.

## Error model and CLI

The validation core returns structured error records containing:

- collection manifest path;
- optional inventory row number;
- stable error code;
- human-readable detail.

Initial codes include:

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

CLI behavior:

```text
python -m tools.validate_collections
```

With no arguments it validates every `collections/*.toml` manifest in lexical order. A positional manifest path may be accepted for focused local testing, but it must obey the same rule that its inventory resolves within the manifest's directory.

Success prints a concise per-collection summary and exits `0`. Failure prints errors in stable path/row/code order and exits `1`. Tooling/runtime misuse exits `2`.

## Testing strategy

Tests use temporary directories and small synthetic manifest/inventory fixtures so failure cases do not require mutating the frozen collection.

Required tests:

1. the committed `base-game-2026-06-16` manifest and inventory validate successfully;
2. SHA-256 drift is rejected;
3. row-count mismatch is rejected;
4. duplicate canonical puzzle ID is rejected;
5. duplicate upstream game puzzle ID is rejected;
6. duplicate leaderboard key is rejected;
7. non-contiguous or out-of-order canonical puzzle IDs are rejected;
8. malformed game puzzle IDs are rejected;
9. malformed groups or invalid puzzle types are rejected;
10. exact CSV header/order is enforced;
11. manifest `group_counts` rollups are validated against finer row groups;
12. unmatched and overlapping rollup declarations are rejected;
13. inventory path traversal is rejected;
14. malformed TOML fails cleanly;
15. repeated runs produce the same ordered error output.

Tests should exercise the public validation function directly; CLI tests are limited to exit-code/output contract where useful.

## Authority and generated-state boundary

The validator does not create a second catalog. The authoritative collection facts remain the checked-in manifest and inventory. The validator derives counts, hashes, and consistency checks from those facts at runtime.

No generated count file, index, cache, or validation ledger is committed. CI may run the validator, but CI output is ephemeral evidence rather than repository state.

## Deferred work

This slice intentionally does not add:

- source adapters;
- source caches;
- puzzle/solution artifact schemas;
- observation or verification schemas;
- `omsim` integration;
- Parquet or Hugging Face dependencies;
- canonical corpus materialization;
- code to rewrite or normalize manifests;
- a general plugin/registry system for collection types.

Those belong to later slices once this collection contract is executable and stable.

## Acceptance criteria

The slice is ready to merge when:

- both JSON Schema files are committed and match the documented contract;
- `python -m tools.validate_collections` validates the frozen 166-puzzle collection with exit code `0`;
- the validator deterministically rejects each specified corruption case;
- the test suite passes using only Python 3.11+ standard-library modules;
- no frozen collection membership or source facts are changed merely to satisfy the validator;
- no generated projection or duplicate catalog is introduced.
