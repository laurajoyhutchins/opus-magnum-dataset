# Hugging Face Export Contract

Status: **Draft v0.1**

Hugging Face is a first-class publication target for the canonical Opus Magnum corpus. It is not the repository's source of truth.

The export must be loading-script-free and Parquet-first so ordinary consumers can use Hugging Face Datasets, Dataset Viewer, direct Parquet access, DuckDB/Arrow tooling, and other tabular systems without executing repository code.

The generic four-config release/export shell is implemented and exercised by the tiny fixture corpus. The remaining work is to connect the complete canonical artifact, verification, and normalization pipeline to those inputs and publish the first real complete corpus.

## 1. Publication model

A single Hugging Face dataset repository should expose multiple configs corresponding to canonical entity classes rather than flattening the whole corpus into one oversized row shape.

Required v1 configs:

- `puzzles`;
- `solutions`;
- `observations`;
- `normalized`.

Optional later configs may include benchmark-specific materializations, frontier views, or release reports, but these must remain derived views over canonical facts. Benchmark semantics are specified separately in [`benchmark-protocol.md`](benchmark-protocol.md).

## 2. Splits

Collection identifiers map to Hugging Face splits.

Example:

```text
config: solutions
split: base_game_2026_06_16
```

Do not use `train`, `validation`, or `test` for the general corpus. Those names are reserved for separately designed benchmark partitions with explicit leakage and evaluation methodology.

A published split is immutable. New official content creates a new collection/split rather than mutating an old one.

## 3. Repository layout

The current v1 release shell emits one Parquet shard per config and collection split:

```text
README.md
data/
  puzzles/
    <collection>-00000-of-00001.parquet
  solutions/
    <collection>-00000-of-00001.parquet
  observations/
    <collection>-00000-of-00001.parquet
  normalized/
    <collection>-00000-of-00001.parquet
```

If corpus size later requires multi-shard output, shard sizing and naming must become an explicit versioned export policy rather than an implicit library behavior.

## 4. `puzzles` config

One row per canonical puzzle identity in the selected collection.

Required columns:

- `puzzle_id`: string;
- `display_name`: string;
- `kind`: string;
- `aliases`: list of structs or equivalent nested representation;
- `canonical_puzzle_artifact_id`: nullable string;
- `puzzle_sha256`: nullable string;
- `puzzle_bytes`: nullable binary, governed by payload policy;
- `rights_status`: string;
- `collection_id`: string.

Raw puzzle bytes must not be duplicated into solution rows.

## 5. `solutions` config

One row per exact canonical solution artifact represented in the selected collection's derived corpus.

Required columns:

- `solution_id`: string;
- `solution_sha256`: string;
- `puzzle_id`: string;
- `puzzle_artifact_id`: string;
- `solution_format`: string;
- `solution_bytes`: nullable binary, governed by payload policy;
- `rights_status`: string;
- `verified`: boolean;
- `validation_profile`: string;
- `verifier_revision`: string;
- `cost`: nullable integer;
- `cycles`: nullable integer;
- `area`: nullable integer;
- `instructions`: nullable integer;
- additional deterministic verifier metrics where available;
- `vanilla_constructible`: nullable boolean;
- `record_eligible`: nullable boolean;
- `normalized_solution_id`: nullable string;
- `source_count`: integer;
- `collection_id`: string.

A source-claimed score is not stored in these computed metric columns. Source claims belong to `observations`.

## 6. `observations` config

One row per provenance observation. An observation may describe an exact artifact sighting or source metadata about an artifact. Metadata is preserved even when the referenced solution bytes were not acquired.

Required columns:

- `observation_id`: string;
- `artifact_kind`: string;
- `artifact_id`: nullable string; null is permitted only for an explicit metadata observation whose referenced artifact is absent;
- `puzzle_id`: nullable string;
- `source_role`: nullable string with canonical values `artifact` or `metadata`; null/omission is retained only for backward-compatible legacy rows;
- `source_id`: string;
- `source_revision`: nullable string;
- `source_object_id`: nullable string;
- `source_path`: nullable string;
- `associated_artifact_path`: nullable string for a source-declared metadata-to-artifact association such as leaderboard `dataPath`;
- `source_declared_puzzle_id`: nullable string preserving the source's own puzzle identifier independently of canonical `puzzle_id`;
- `source_url`: nullable string;
- `author`: nullable string;
- `retrieved_at`: timestamp;
- source-claimed metrics as nullable typed columns;
- `observed_sha256`: nullable string for the associated artifact bytes when available;
- `source_evidence_sha256`: nullable string identifying the source evidence bytes;
- `source_evidence_byte_length`: nullable integer;
- `rights_status`: string;
- `importer_version`: string.

This config preserves the many-to-one relationship between upstream appearances and canonical artifacts. A metadata-only row with `artifact_id = null` remains a source fact rather than being discarded merely because the source-referenced solution artifact is missing from the cache.

## 7. `normalized` config

One row per successfully normalized solution.

Required columns:

- `normalized_solution_id`: string;
- `solution_id`: string;
- `puzzle_id`: string;
- `normalizer_version`: string;
- `parts`: nested list of structs;
- `tracks`: nested list of structs;
- `programs`: nested list of structs;
- deterministic histograms/summaries useful for analysis and ML.

The exact nested schema is versioned separately from the artifact identity model.

A solution may be verified while having no normalized row if normalization fails or is unsupported.

## 8. Referential integrity

Within one published corpus release:

- every `solutions.puzzle_id` must exist in `puzzles`;
- every `normalized.solution_id` must exist in `solutions`;
- every non-null `observations.artifact_id` must resolve to its declared canonical artifact class;
- `observations.artifact_id` may be null only when `source_role` is explicitly `metadata`, preserving metadata about an artifact that is not present in the canonical artifact set;
- all references use canonical stable IDs, not row offsets or file paths.

Hugging Face does not enforce cross-config foreign keys, so the exporter and release validation must enforce them before publication.

## 9. Payload policy

The exporter supports at least two modes:

```text
metadata-only
include-permitted
```

### `metadata-only`

Raw puzzle and solution byte columns are null under the current v1 schemas. Provenance, hashes, computed metrics, coverage, and otherwise publishable derived structures remain available.

### `include-permitted`

Raw bytes are included only for artifacts whose rights policy explicitly allows redistribution.

The exporter must never infer permission from technical accessibility or from the repository's own code license.

The release validator reapplies the selected payload policy to generated Parquet before staging/publication.

## 10. Determinism

Rows are emitted in deterministic order.

Minimum ordering rules:

- puzzles: `puzzle_id` ascending;
- solutions: `(puzzle_id, solution_id)` ascending;
- observations: `(artifact_id, observation_id)` ascending;
- normalized: `(puzzle_id, solution_id)` ascending.

Nested lists whose ordering is not semantically meaningful must nevertheless use a versioned deterministic ordering rule.

Given identical canonical corpus state and exporter version, logical row content must be identical. Release manifests record both logical-record hashes and generated Parquet hashes; canonical reproducibility is defined primarily over logical content and the release manifest rather than assuming writer-independent byte identity.

## 11. Dataset card

The generated Hugging Face `README.md` must contain or declare:

- dataset purpose;
- corpus schema version;
- collection identifier;
- release manifest hash;
- build software revision;
- verifier implementation/revision;
- validation profile;
- normalizer version;
- source classes and pinned revisions where publishable;
- puzzle count;
- candidate/verified/rejected solution counts;
- per-puzzle coverage summary or linked generated table;
- payload policy;
- rights/licensing caveats;
- citation/attribution guidance;
- reproducibility command;
- known limitations.

The dataset card is generated from release metadata. Do not maintain release counts or source revisions manually in a second document.

## 12. Dataset Viewer compatibility

Every published release must be compatible with the Hugging Face Dataset Viewer without requiring remote Python code.

Release validation should check:

1. dataset/config/split discovery succeeds;
2. first rows render for every required config/split;
3. Parquet shard discovery succeeds;
4. schema matches the versioned export contract;
5. expected row counts match the canonical release manifest;
6. no forbidden payload bytes are present under the selected payload policy.

Local release validation already enforces schemas, cross-config references, release-manifest integrity, output hashes, coverage policy, and payload policy. Hub/Dataset Viewer checks remain publication-boundary validation.

## 13. Local consumption contract

The generated repository should support ordinary usage such as:

```python
from datasets import load_dataset

solutions = load_dataset(
    "<namespace>/opus-magnum-dataset",
    "solutions",
    split="base_game_2026_06_16",
)
```

Consumers must not need this Git repository, a custom loader, `trust_remote_code`, or the verifier merely to read already-published rows.

## 14. Publication flow

Conceptually:

```text
pinned source cache
      ↓
canonical corpus build
      ↓
verification + normalization
      ↓
release manifest
      ↓
Hugging Face exporter
      ↓
Parquet shards + generated dataset card
      ↓
release validation
      ↓
publish
```

Publication is downstream of a completed canonical release. It does not fetch or reconcile upstream source material itself.

The implemented release commands are:

```text
opus-corpus release build <collection> --input <path> --output <path> ...
opus-corpus release validate <collection> --output <path>
opus-corpus release stage <collection> --output <path> --destination <path>
opus-corpus release publish <collection> --output <path>
```

## 15. Required invariants

HF-1. Every stable corpus release produces a loading-script-free Hugging Face export.

HF-2. `puzzles`, `solutions`, `observations`, and `normalized` are independently loadable configs.

HF-3. Collection identities map deterministically to immutable splits.

HF-4. Hugging Face artifacts are generated exclusively from canonical corpus state.

HF-5. Exported logical rows and schemas are deterministic for a fixed canonical manifest and exporter version.

HF-6. Payload inclusion obeys source rights policy independently from metadata publication.

HF-7. The generated dataset card identifies the corpus manifest, schema, verifier, validation profile, source revisions, coverage, and payload policy.

HF-8. Publication passes Dataset Viewer validation and ordinary `datasets.load_dataset()` access without remote code execution.

HF-9. No canonical relationship depends on Parquet row order or shard boundaries.

HF-10. Benchmark train/dev/test partitions, if later added, are separately specified derived configs and never retroactively redefine the general corpus splits.

## 16. Settled and remaining publication decisions

The current release shell settles several early exporter choices:

- Arrow/Parquet implementation: `pyarrow==21.0.0`;
- compression: `zstd`;
- one deterministic shard per config/split for v1;
- required configs: `puzzles`, `solutions`, `observations`, and `normalized`;
- collection-to-split mapping by replacing `-` with `_`;
- metadata-only raw byte fields are null under the current schemas;
- default payload policy is `metadata-only`;
- schema and logical-row ordering are repository-controlled rather than inferred from Hugging Face.

Remaining publication decisions include:

- final Hugging Face namespace/repository name (`corpus.toml` intentionally retains `CHANGE_ME`);
- publication credentials and automation policy;
- whether future payload-bearing releases share one Hub repository with metadata-only releases or use separate repositories;
- Dataset Viewer acceptance checks against the first complete real corpus;
- any future multi-shard sizing policy if one-file-per-config ceases to be practical.

These are publication-boundary decisions. They must not create a second canonical corpus model or alter immutable collection identities.
