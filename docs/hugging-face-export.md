# Hugging Face Export Contract

Status: **Draft v0.1**

Hugging Face is a first-class publication target for the canonical Opus Magnum corpus. It is not the repository source of truth.

The export is loading-script-free and Parquet-first so ordinary consumers can use Hugging Face Datasets, Dataset Viewer, direct Parquet access, DuckDB/Arrow tooling, and other tabular systems without executing repository code.

The generic four-config release/export shell, semantic puzzle release materialization, and deterministic offline v1 runner are implemented. Completing the first real release still requires a complete pinned exact-puzzle cache, the real 166-puzzle build, and publication to the explicitly configured `laurajoyhutchins/opus-magnum` destination.

## 1. Publication model

One Hugging Face dataset repository exposes independently loadable canonical configs:

- `puzzles`;
- `solutions`;
- `observations`;
- `normalized`.

Optional benchmark/frontier/report configs may be added later only as derived views over canonical facts. Benchmark semantics remain separately specified in [`benchmark-protocol.md`](benchmark-protocol.md).

## 2. Splits

Collection identifiers map to immutable Hugging Face splits. For example:

```text
config: solutions
split: base_game_2026_06_16
```

The general corpus does not use `train`, `validation`, or `test`; those names are reserved for explicitly designed benchmark partitions.

## 3. Repository layout

The current v1 release shell emits one Parquet shard per config and collection split plus the release manifest and generated Hub documentation:

```text
README.md
LICENSE
release-manifest.json
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

If corpus size later requires multiple shards, shard sizing and naming become an explicit versioned export policy.

## 4. `puzzles` config

One row per canonical semantic `PuzzleDefinition` in the selected collection.

Required semantic columns include:

- `puzzle_definition_id`;
- `schema_version`;
- `puzzle_id`;
- `allowed_parts`;
- `allowed_instructions`;
- `reagents`;
- `products`;
- `output_scale`;
- `target_output_count`;
- `production`;
- `production_constraints`;
- `source_observation_ids`;
- `puzzle_artifact_ids`.

Collection presentation columns are:

- `display_name`;
- `kind`;
- `aliases`;
- `collection_id`.

The `puzzles` config is semantic, not a binary-artifact table. It does not contain `puzzle_bytes`, `puzzle_sha256`, `rights_status`, or a single canonical puzzle-artifact ID. Zero, one, or multiple exact `PuzzleArtifact` records may support the same semantic definition.

Exact puzzle artifacts remain represented through their provenance observations and semantic lineage IDs. They remain the verifier boundary where byte identity matters.

## 5. `solutions` config

One row per exact canonical solution artifact represented in the selected collection's derived corpus.

Required columns include:

- `solution_id`;
- `solution_sha256`;
- `puzzle_id`;
- `puzzle_artifact_id`;
- `solution_format`;
- `solution_bytes`: nullable binary governed by payload policy;
- `rights_status`;
- `verified`;
- `validation_profile`;
- `verifier_revision`;
- recomputed `cost`, `cycles`, `area`, and `instructions`;
- `vanilla_constructible`;
- `record_eligible`;
- `normalized_solution_id`;
- `source_count`;
- `collection_id`.

`puzzle_artifact_id` preserves the exact puzzle bytes used for verification. It must refer to an artifact listed by that puzzle's semantic definition. Source-claimed scores are not stored in computed metric columns; they belong to `observations`.

## 6. `observations` config

One row per provenance observation. An observation may describe an exact artifact sighting or metadata/semantic evidence.

Required fields include source identity/revision/path, retrieval time, source role, puzzle identity, artifact identity when present, source evidence hashes/lengths, source-declared metrics where present, rights status, and importer version.

A metadata observation may have `artifact_id = null`. Exact puzzle observations may refer to any `PuzzleArtifact` listed in the corresponding `PuzzleDefinition.puzzle_artifact_ids`.

This config preserves many-to-one source evidence rather than collapsing provenance into release rows.

## 7. `normalized` config

One row per successfully normalized solution, including:

- `normalized_solution_id`;
- `solution_id`;
- `puzzle_id`;
- `normalizer_version`;
- normalized parts, tracks, programs, and deterministic summaries.

Every normalized solution derives from one exact `SolutionArtifact`. The generic release schema can represent a verified solution without a normalized row, but the canonical v1 runner is stricter: every verifier-parseable solution is normalized, and normalization rejection fails the v1 build closed.

## 8. Referential integrity

Within one release:

- every `solutions.puzzle_id` exists in `puzzles`;
- every `solutions.puzzle_artifact_id` exists in the referenced puzzle definition's `puzzle_artifact_ids`;
- every `normalized.solution_id` exists in `solutions`;
- every exact puzzle observation resolves to a puzzle artifact listed by a released semantic definition;
- every solution observation resolves to a released solution;
- metadata observations may omit `artifact_id` only when explicitly represented as metadata;
- all relationships use canonical IDs, never row offsets or source file paths.

Hugging Face does not enforce these relationships, so release materialization and validation must do so before publication.

## 9. Payload and rights policy

The exporter supports:

```text
metadata-only
include-permitted
```

Puzzle release rows contain semantic structures and never contain raw puzzle bytes. Puzzle-artifact redistribution rights remain attached to artifact provenance rather than being projected onto semantic definitions.

For `solutions`, `metadata-only` requires `solution_bytes` to be null. `include-permitted` may include solution bytes only when the exact artifact's `rights_status` is `redistributable`.

Technical accessibility never implies redistribution permission. Repository-authored code is MIT-licensed, while third-party corpus material retains source-specific rights. The staged dataset card therefore declares:

```yaml
license: other
license_name: Mixed/source-specific rights
```

The staged projection also contains a generated `LICENSE` rights notice derived from repository rights policy.

## 10. Determinism

Rows use deterministic ordering:

- puzzles: `puzzle_id`;
- solutions: `(puzzle_id, solution_id)`;
- observations: `(artifact_id, observation_id)`;
- normalized: `(puzzle_id, solution_id)`.

Semantic canonicalization belongs to `PuzzleDefinition`; the exporter does not create another puzzle-normalization path. Given identical canonical state and exporter version, logical row content is identical.

Release manifests record logical-record and Parquet hashes. `opus-corpus release v1` runs the complete offline materialization/release pipeline twice from the same pinned cache and refuses publication unless canonical release-manifest bytes match.

## 11. Dataset card

The generated Hub `README.md` must identify at least:

- mixed/source-specific rights metadata;
- dataset purpose and corpus schema version;
- collection identity;
- release manifest hash and build revision;
- verifier implementation/revision and validation profile;
- normalizer version;
- source classes/revisions where publishable;
- puzzle and solution coverage counts;
- payload policy;
- rights caveats and staged `LICENSE` notice;
- reproducibility command and known limitations.

Release counts, source revisions, and rights summaries are generated from canonical release facts, not maintained independently on the Hub.

## 12. Dataset Viewer compatibility

A published release must load without remote Python code. Publication validation should confirm config/split discovery, first-row rendering, Parquet discovery, schema agreement, row-count agreement with the manifest, and absence of forbidden payload bytes.

Local release validation already checks schemas, cross-config references, manifest integrity, output hashes, coverage policy, and payload policy.

## 13. Local consumption contract

Ordinary usage should work directly:

```python
from datasets import load_dataset

solutions = load_dataset(
    "laurajoyhutchins/opus-magnum",
    "solutions",
    split="base_game_2026_06_16",
)
```

Consumers do not need this Git repository, a custom loader, `trust_remote_code`, or a verifier merely to read an already-published release.

## 14. Publication flow

```text
pinned source cache
      ↓
artifact + observation materialization
      ↓
PuzzleDefinition reconciliation
      ↓
exact verification + solution normalization
      ↓
canonical four-config release
      ↓
release manifest
      ↓
Hub staging + validation
      ↓
publish
```

`release v1` is network-free. It consumes pinned cache facts and an explicitly provisioned, hash-pinned `libverify` shared library. It requires verifier-ready exact puzzle coverage before verification, preserves verifier failures, normalizes every verifier-parseable solution, and atomically promotes output only after a second full rebuild reproduces the first manifest.

Staging and publication are separate downstream operations. Publication credentials are explicit operator inputs and are never committed by the runner.

## 15. Required invariants

HF-1. Every stable corpus release produces a loading-script-free Hugging Face export.

HF-2. The four canonical configs are independently loadable.

HF-3. Collection identities map deterministically to immutable splits.

HF-4. Hub artifacts derive exclusively from canonical corpus state.

HF-5. Exported logical rows and schemas are deterministic for fixed canonical state and exporter version.

HF-6. Puzzle semantic publication is independent from raw puzzle-artifact redistribution; solution payload inclusion obeys exact-artifact rights policy.

HF-7. The generated dataset card identifies manifest, schema, verifier, source revisions, coverage, payload policy, and mixed/source-specific rights.

HF-8. Publication passes Dataset Viewer and ordinary `datasets.load_dataset()` access without remote code.

HF-9. No canonical relationship depends on Parquet row order or shard boundaries.

HF-10. Later benchmark train/dev/test partitions are separately specified derived configs and never redefine general corpus splits.

## 16. Settled and remaining publication decisions

Settled v1 choices include:

- `pyarrow==21.0.0` with `zstd` compression;
- one deterministic shard per config/split;
- configs `puzzles`, `solutions`, `observations`, and `normalized`;
- collection-to-split mapping by replacing `-` with `_`;
- semantic, payload-free `puzzles` rows;
- solution-only release payload field governed by payload policy;
- default `metadata-only` publication;
- repository-controlled schema and row ordering;
- Hub identity `laurajoyhutchins/opus-magnum`;
- `license: other` / `Mixed/source-specific rights` metadata;
- generated staged rights notice.

Remaining publication decisions include credentials/automation policy, source-specific redistribution conclusions still unresolved, Dataset Viewer acceptance against the first complete corpus, and future multi-shard sizing if required.

None of those decisions may create a second canonical corpus model or alter immutable collection identities.
