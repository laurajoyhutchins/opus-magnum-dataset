# Hugging Face template adoption design

Status: approved direction, ready for implementation planning
Date: 2026-08-23

## Goal

Adopt the proven generic build, validation, Parquet, manifest, staging, and Hugging Face publication machinery from `laurajoyhutchins/hugging-face-dataset-template` without creating a second generic dataset framework inside the Opus Magnum project.

The Opus Magnum repository remains authoritative for collection definitions, source facts, canonical corpus semantics, verification policy, rights policy, normalization, and release composition. Hugging Face remains a generated distribution surface.

## Scope

This design adds the infrastructure needed for the first real end-to-end corpus slice:

- one self-contained Python package and CLI in this repository;
- JSON Schema execution using Draft 2020-12;
- deterministic hashing of source inputs and logical records;
- deterministic multi-config/multi-split Parquet materialization;
- release-manifest generation and validation;
- explicit `metadata-only` and `include-permitted` payload policies;
- generated Hugging Face dataset-card metadata and release facts;
- staging and publication of only generated release artifacts;
- CI validation of collection definitions and generated release semantics;
- strict dependency pinning sufficient to make the build environment explicit.

This design does not yet add full upstream acquisition, `omsim` verification, normalization, Pareto derivation, or complete source coverage. It creates the reusable release shell those Opus-specific stages will feed.

## Existing assets

### Opus Magnum repository

The repository already defines:

- the canonical corpus entities and release invariants in `docs/dataset-spec.md`;
- the Hugging Face publication contract in `docs/hugging-face-export.md`;
- the frozen `base-game-2026-06-16` collection manifest and 166-row inventory;
- source coverage and rights boundaries in `docs/source-inventory.md`;
- a proposed collection validator design in `docs/superpowers/specs/2026-08-23-collection-validator-design.md`.

### Hugging Face dataset template

The template already provides working patterns for:

- TOML configuration;
- JSON Schema validation;
- stable source ordering;
- source SHA-256 hashes;
- canonical logical-record hashing;
- Parquet output;
- build manifests;
- post-build validation;
- Hub staging and publication;
- Python packaging and CLI wiring;
- test and GitHub Actions structure.

These generic mechanisms should be reused rather than independently re-designed.

## Approaches considered

### 1. Copy and adapt the template implementation into this repository — selected

Vendor the small generic pipeline implementation as repository-owned source, then adapt it to Opus Magnum's multi-config release model.

Benefits:

- the Opus build is self-contained and reproducible from one repository revision;
- no runtime availability or version-skew dependency on another repository;
- the adopted code can evolve specifically around the Opus release contract;
- provenance is still clear because the initial adoption commit can identify the source template revision;
- operational machinery remains minimal.

Trade-off: generic improvements made later to the template are not inherited automatically. That is intentional. Reuse is by adoption of a known implementation, not by creating another live authority.

### 2. Depend on the template repository as an installable package

This would avoid copying code, but it couples reproducible Opus releases to another repository's packaging and release discipline. It also makes the template a runtime authority over Opus builds.

Rejected.

### 3. Git subtree/submodule or periodic synchronization

This preserves a visible relationship with the template but introduces synchronization machinery and a second moving source of implementation state.

Rejected. The project prefers fewer active mechanisms and one authoritative implementation path.

## Architecture

The repository gains one Python package, provisionally `opus_corpus`, with a narrow pipeline boundary:

```text
pinned/raw source facts
        |
        v
Opus-specific adapters / verifier / normalizer
        |
        v
canonical release tables
        |
        v
schema + semantic validation
        |
        v
Parquet configs + release manifest + generated dataset card
        |
        v
release validation
        |
        v
Hugging Face projection
```

The generic release layer never interprets Opus solution semantics. It receives canonical rows, schemas, release metadata, and payload-policy decisions from Opus-specific code.

## Repository layout

The implementation should converge on this layout:

```text
pyproject.toml
uv.lock
schemas/
  collection-manifest.schema.json
  collection-inventory-row.schema.json
  puzzle.schema.json
  solution.schema.json
  observation.schema.json
  normalized.schema.json
src/opus_corpus/
  __init__.py
  __main__.py
  cli.py
  config.py
  errors.py
  hashing.py
  collections.py
  release.py
  parquet.py
  card.py
  publish.py
tests/
  test_collections.py
  test_release.py
  test_parquet.py
  test_card.py
  test_publish.py
fixtures/
  tiny-corpus/
    ...
.github/workflows/
  validate.yml
  publish.yml
```

Generated release artifacts are not authoritative repository state and should not be committed unless a later release policy explicitly requires them.

## Configuration model

Use one repository-level TOML configuration file for generic build/publication settings. Collection membership continues to live in `collections/*.toml` plus the referenced CSV inventory.

The build configuration must declare:

- schema version;
- output root;
- Hugging Face repository ID and privacy setting;
- Parquet compression and deterministic writer settings;
- payload policy default;
- release-card generation settings;
- required config names: `puzzles`, `solutions`, `observations`, `normalized`.

Collection identity is supplied explicitly to build commands and maps to the immutable Hugging Face split name by replacing hyphens with underscores, for example `base-game-2026-06-16` -> `base_game_2026_06_16`.

Do not use `train`, `validation`, or `test` for the general corpus.

## Collection validation

The semantic rules from `2026-08-23-collection-validator-design.md` remain valid, including:

- manifest schema validation;
- inventory hash validation;
- exact ordered CSV header;
- row schema validation;
- uniqueness of canonical puzzle ID, game puzzle ID, and leaderboard key;
- contiguous ordered canonical puzzle IDs;
- row count agreement;
- group-rollup coverage and count agreement;
- deterministic ordered errors.

However, the proposed standalone standard-library validator toolchain is superseded by this design. Collection validation should use the same Python package, error model, JSON Schema dependency, test runner, and CLI as the rest of the corpus pipeline.

There must still be exactly one authoritative collection catalog: the checked-in manifest and inventory. Validation derives facts from them and commits no generated ledger or secondary index.

## Canonical release inputs

The generic release layer consumes four canonical row streams keyed by config name:

- `puzzles`;
- `solutions`;
- `observations`;
- `normalized`.

Each stream is validated against its versioned JSON Schema before Parquet materialization.

The first implementation may use JSONL fixtures as the handoff representation for the tiny vertical slice. JSONL is not a new authority; it is an intermediate fixture/build input that will later be generated by the Opus-specific acquisition and verification stages.

Rows are sorted before hashing and writing using the existing export contract:

- puzzles: `puzzle_id`;
- solutions: `(puzzle_id, solution_id)`;
- observations: `(artifact_id, observation_id)`;
- normalized: `(puzzle_id, solution_id)`.

## Payload policy

Every build selects one explicit payload policy:

### `metadata-only`

Raw puzzle and solution byte fields must be absent or null according to the versioned schema policy. The build fails if restricted payload bytes would be published.

### `include-permitted`

Raw bytes may be included only when the row's artifact rights status is exactly `redistributable`. Rows with `local_fetch_only` or `unknown` rights must have publishable byte fields null/absent.

The release layer does not infer rights from source accessibility, repository license, or prior successful publication.

Payload-policy validation occurs before Parquet writing and again when validating generated Parquet rows so a serialization or staging bug cannot bypass the policy.

## Release manifest

One generated release manifest describes the full multi-config release. It records at least:

- manifest format version;
- corpus schema version;
- collection ID and collection inventory hash;
- build software Git revision when available;
- build configuration hash;
- payload policy;
- verifier revision/hash when the input metadata supplies it;
- validation profile version when supplied;
- normalizer version when supplied;
- per-config schema paths and hashes;
- per-config logical-record hashes;
- per-config row counts;
- per-config Parquet file paths and SHA-256 hashes;
- source/input file hashes used for the release;
- coverage counts supplied by canonical corpus state;
- overall logical release hash derived from the canonical manifest content.

The manifest is generated. Counts and hashes are never hand-maintained in README files or secondary ledgers.

## Parquet determinism

Adopt the template's use of PyArrow and Zstandard compression, but make the writer configuration explicit and version-controlled.

Logical row reproducibility is the normative v1 promise. Each config receives a canonical logical-record hash independent of Parquet encoding.

The implementation also records physical Parquet SHA-256 hashes. Byte-for-byte Parquet reproducibility must not be claimed until CI demonstrates it under the pinned dependency/toolchain environment.

The project uses a committed lockfile. The minimum supported Python version is 3.12 to match the adopted template unless a concrete compatibility requirement justifies lowering it.

## Dataset card generation

The repository README remains a development/project document. The Hugging Face dataset card is generated separately from release metadata.

The generated card must include YAML config metadata mapping each config to the immutable collection split and Parquet path, plus release facts required by `docs/hugging-face-export.md`:

- purpose;
- corpus schema version;
- collection identifier;
- release manifest hash;
- build software revision;
- verifier and validation profile;
- normalizer version;
- source classes/revisions where publishable;
- puzzle/candidate/verified/rejected counts;
- coverage summary;
- payload policy;
- rights/licensing caveats;
- reproducibility command;
- known limitations.

No release count or source revision is manually duplicated in a checked-in card.

## Hugging Face staging and publication

Publication remains downstream of a successful local build and validation.

Staging contains only generated distribution artifacts:

```text
README.md
release-manifest.json
data/
  puzzles/<split>-00000-of-....parquet
  solutions/<split>-00000-of-....parquet
  observations/<split>-00000-of-....parquet
  normalized/<split>-00000-of-....parquet
```

Source caches, raw local-only payloads, schemas, tests, code, and internal build fixtures are never staged merely because they exist in the GitHub repository.

Publishing validates first, refuses placeholder/malformed Hub repository IDs, creates the dataset repository if needed, and replaces the remote generated projection so stale generated files do not survive.

## CLI

One CLI owns both collection validation and release operations. Proposed commands:

```text
opus-corpus collections validate [manifest]
opus-corpus release build <collection> --input <path> --payload-policy metadata-only
opus-corpus release validate <collection> --output <path>
opus-corpus release stage <collection> --output <path> --destination <path>
opus-corpus release publish <collection> --output <path>
```

Future acquisition and verification commands may be added under the same CLI, but are out of scope for this slice.

## Error model

Use typed repository exceptions for configuration, schema, collection, release, payload-policy, and publication failures.

Validation errors must identify:

- the affected collection/config;
- the input path where applicable;
- the row/record identity or line number where applicable;
- a stable machine-readable error code;
- concise human-readable detail.

Validation should accumulate independent deterministic errors where practical rather than fail after the first row defect. Operational misuse and missing runtime dependencies remain distinct from data-validation failures.

## Testing

Implementation follows test-driven development.

Required tests include:

1. the committed 166-puzzle frozen collection validates;
2. every corruption case from the earlier collection-validator design is rejected;
3. each canonical config rejects schema-invalid fixture rows;
4. row sorting is deterministic and independent of fixture file order;
5. repeated logical builds produce identical logical-record and release hashes;
6. metadata-only mode rejects any publishable puzzle/solution byte payload;
7. include-permitted mode permits bytes only for `redistributable` rows;
8. generated Parquet round-trips back to schema-valid canonical rows;
9. generated dataset-card YAML maps all four configs to the immutable collection split;
10. generated dataset-card counts and revisions come from release metadata rather than checked-in prose;
11. staging contains only the generated projection allowlist;
12. publication refuses placeholder repository IDs;
13. the tiny fixture corpus builds and validates end-to-end;
14. CI runs collection validation, unit tests, and tiny-corpus build/validation.

Tests must not require network access. Hub upload behavior should be tested at the staging/configuration boundary; live publication is exercised only by the explicit publish workflow.

## Tiny vertical slice acceptance criteria

This adoption is complete when one command sequence can:

1. validate `base-game-2026-06-16` collection metadata;
2. build a tiny fixture release containing at least one puzzle plus representative solution/observation/normalized rows;
3. enforce the chosen payload policy;
4. produce all four Parquet configs for the collection split;
5. emit a release manifest with logical and physical hashes;
6. generate the Hugging Face dataset card;
7. validate the generated release from disk;
8. stage only the expected Hub projection;
9. pass the full local/CI test suite from the committed lockfile environment.

This proves the release factory before full upstream acquisition and verification are added.

## Explicit non-goals

This slice does not:

- duplicate the template as a live dependency;
- introduce a plugin/registry framework;
- add a database service;
- add a second collection catalog;
- commit generated validation ledgers or release counts;
- implement full source acquisition;
- implement `omsim` integration;
- claim complete solution coverage;
- claim raw payload redistribution rights;
- claim byte-identical Parquet reproducibility before it is demonstrated.

## Superseded design decisions

`docs/superpowers/specs/2026-08-23-collection-validator-design.md` remains useful for its collection semantic rules and test cases, but its decision to introduce a separate Python-standard-library-only validator toolchain is superseded by this design. The collection validator becomes one component of the single adopted corpus toolchain.
