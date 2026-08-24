# Dataset Specification

Status: **Draft v0.1**

This document defines the canonical data model and release contract for the Opus Magnum dataset project. It is intentionally independent of any one upstream archive, directory layout, parser, publication platform, or machine-learning framework.

## 1. Product definition

The project builds reproducible corpora of Opus Magnum puzzles and solutions from pinned source facts.

The repository contains:

- collection definitions;
- source declarations;
- schemas;
- deterministic acquisition, verification, normalization, derivation, reporting, and export software;
- small test fixtures;
- release manifests.

The repository does **not** treat generated corpus files or a manually maintained solution index as authoritative state.

## 2. Required use cases

The canonical model must support:

1. puzzle/solution benchmarking;
2. exact metric verification;
3. solver and optimizer evaluation;
4. imitation-learning and representation-learning datasets;
5. Pareto/frontier analysis;
6. provenance and archival research;
7. reproducible dataset releases;
8. export to Hugging Face and generic Parquet/JSONL consumers.

Benchmark-specific protocol, attempt, scoring, contamination, and split rules are defined separately in [`benchmark-protocol.md`](benchmark-protocol.md). The corpus model supplies benchmark facts; it does not bake one benchmark methodology into canonical entities.

## 3. Collections

A **collection** is an immutable, explicit set of canonical puzzle identities.

Examples may include:

- a frozen base-game snapshot;
- a particular Journal range;
- De Re Metallica;
- official production puzzles;
- a tournament or community collection.

A collection identifier must be versioned or dated. A mutable alias such as `current` may exist only as a convenience pointer and must never be used as the identity of a published corpus release.

The first frozen collection is `base-game-2026-06-16`, whose 166-puzzle membership is committed in `collections/base-game-2026-06-16.csv`. Its membership is repository authority; pinned upstream inventories are evidence for that frozen definition rather than alternate mutable collection authorities.

## 4. Canonical entities

### 4.1 Puzzle

A stable conceptual identity for one puzzle.

Required fields:

- `puzzle_id`: repository-defined stable identifier;
- `display_name`;
- `kind`: campaign, production, journal, expansion, custom, etc.;
- `collection_memberships`;
- `aliases`: upstream IDs/names associated with the puzzle.

`puzzle_id` must not depend on a localized title, source filename, source directory path, or artifact hash.

### 4.2 PuzzleArtifact

One exact byte representation of a puzzle.

Required fields:

- `puzzle_artifact_id`;
- `puzzle_id`;
- `sha256`;
- `byte_length`;
- `format`;
- `rights_status`;
- provenance links.

One puzzle may have multiple artifacts when different upstream transcriptions or versions exist.

### 4.3 SolutionArtifact

One exact source solution artifact.

Required fields:

- `solution_id`;
- `sha256`;
- `byte_length`;
- `format`;
- optional declared/embedded puzzle identity;
- `rights_status`.

Exact byte identity is the v1 deduplication boundary. Two different byte strings are distinct solution artifacts even when they appear semantically equivalent.

### 4.4 Observation

A provenance assertion that an upstream source exposed a puzzle or solution artifact, or metadata about one.

Required fields:

- `observation_id`;
- `source_id`;
- immutable upstream revision/object identity where possible;
- upstream path or object key;
- retrieved timestamp;
- observed artifact hash when bytes were available;
- source author/submitter where available;
- source-declared metrics where available;
- rights/license metadata where available;
- importer version.

Multiple observations may point to the same artifact.

### 4.5 Verification

A deterministic evaluation of one `PuzzleArtifact` + `SolutionArtifact` pair under one verifier and validation profile.

Required fields:

- `verification_id`;
- `puzzle_artifact_id`;
- `solution_id`;
- verifier implementation and revision;
- verifier binary/content hash where practical;
- validation profile version;
- parse status;
- simulation status;
- computed metrics;
- structured error details on failure.

Minimum computed metrics for a successful verification:

- `cost`;
- `cycles`;
- `area`;
- `instructions`.

Additional verifier-supported structural and execution metrics should be retained when deterministic and inexpensive to compute.

## 5. Source facts versus derived state

Source facts are immutable inputs. Derived state is always reproducible from source facts plus pinned software/configuration.

Examples of derived state:

- verification success;
- recomputed metrics;
- normalized machine representation;
- `vanilla_constructible`;
- `record_eligible`;
- Pareto membership;
- best-per-metric selections;
- coverage summaries;
- benchmark selections and reports;
- Hugging Face Parquet files.

Derived state must not be maintained by agents or hand-edited as a second authority.

## 6. Source adapters

Each upstream source is implemented as an independent adapter that emits source facts for later canonical materialization.

Current source classes include:

- historical solution material from `om-archive`;
- current solution payloads and record/frontier metadata from `om-leaderboard`;
- pinned campaign puzzle transcriptions from `omsim`;
- semantic puzzle evidence from `molecule-db` without claiming exact official byte identity;
- explicitly mapped local official `.puzzle` bytes through the `official-game` adapter.

Planned source classes may include clearly identified machine-generated baselines such as OpusSolver output.

No adapter may redefine canonical puzzle IDs, validation semantics, or output schema. Source acquisition also does not make source-declared metrics authoritative; verification remains a separate derived stage.

## 7. Provenance requirements

Every published puzzle or solution row must be traceable to at least one `Observation`.

If the same exact artifact is recovered from multiple sources, preserve one artifact plus multiple observations.

If a source claims metrics that disagree with deterministic verification, preserve both facts. For example:

```text
source_claim.cycles = 169
verification.cycles = 170
```

The verifier result is authoritative for fields explicitly defined as computed metrics; the source claim remains authoritative as a historical observation.

## 8. Verification policy

No solution enters a `verified` derived view because of a filename, leaderboard score, README, or source assertion.

The v1 verification gate requires:

1. successful parsing of the selected canonical puzzle artifact;
2. successful parsing of the solution artifact;
3. successful completion under the pinned simulator/verifier;
4. deterministic metric extraction.

Validation profiles are versioned. Distinct concepts must remain distinct predicates, including:

- simulator-valid;
- ordinary in-game constructible;
- record-eligible.

Anomalous but simulatable solutions should be represented, not silently discarded, unless a specific derived view excludes them.

## 9. Rights and payload policy

Technical ability to store bytes does not imply redistribution permission.

Each artifact carries a `rights_status`, with at least:

- `redistributable`;
- `local_fetch_only`;
- `unknown`.

Build and export software must support metadata-only publication when raw bytes may not be redistributed.

The project must be able to publish hashes, provenance, computed metrics, normalized structures derived where legally appropriate, and acquisition recipes without publishing restricted source bytes.

Repository-authored material is licensed under MIT, while [`../RIGHTS.md`](../RIGHTS.md) defines the repository-wide boundary between that license and third-party corpus material. The MIT license must not be interpreted as relicensing official puzzle bytes, externally authored solution payloads, or other upstream artifacts. `rights_status` remains a provenance-bearing publication policy fact, not a substitute copyright license.

## 10. Deduplication

V1 performs only exact-byte deduplication by SHA-256.

Do not collapse solutions merely because they are:

- translated;
- rotated;
- reflected;
- serialized in a different object order;
- instruction-equivalent;
- score-equivalent;
- apparently machine-equivalent.

Semantic equivalence may be added later as a separately versioned derived clustering algorithm.

## 11. Normalized representations

Normalization is derived state. It is neither artifact identity nor verification authority.

### 11.1 Normalized puzzle representation

A normalized puzzle row must identify both the conceptual puzzle and the exact bytes from which it was derived. At minimum it records:

- `normalized_puzzle_id`;
- `puzzle_id`;
- `puzzle_artifact_id`;
- `normalizer_version`;
- allowed parts/components;
- reagent and product molecules with atom types, bonds, and axial hex coordinates;
- puzzle-specific constraints.

`puzzle_artifact_id` is derivation lineage to an exact `PuzzleArtifact`; it is not a replacement for upstream provenance. Source observations remain attached to the artifact layer.

### 11.2 Normalized solution representation

The normalized solution schema should represent, at minimum:

- parts with type, position, orientation, and type-specific parameters;
- tracks as coordinate sequences;
- arm programs as arm identity plus cycle/opcode entries;
- useful deterministic histograms and geometric summaries.

### 11.3 Serialization projections

Serializers are deterministic projections over normalized records. Serializer format and version are separate from normalizer version. The current baseline is canonical JSON; future compact or model-oriented text formats must be generated from the same normalized records rather than maintained as another authority.

`normalized-puzzle.schema.json` defines the normalized puzzle domain contract. It does not, by itself, add a fifth release config; release wiring for normalized puzzles must be specified explicitly when the materialization pipeline is ready to emit them.

The normalizer version must be recorded for every normalized row.

A normalization failure must not destroy or invalidate a successfully verified raw artifact.

## 12. Derived views

The corpus should deterministically support views such as:

- all verified solutions;
- ordinary/vanilla constructible solutions;
- record-eligible solutions;
- Pareto frontiers over selected metric tuples;
- best cost;
- best cycles;
- best area;
- best instructions;
- human-observed solutions;
- generated baselines;
- one-per-puzzle benchmark selections.

These are queries/materializations over canonical facts, not separately curated corpora. Benchmark-specific selection and evaluation semantics belong to [`benchmark-protocol.md`](benchmark-protocol.md).

## 13. Coverage semantics

Coverage is explicit and puzzle-scoped.

Suggested states:

- `uncovered`: no candidate solution observed;
- `candidate_found`: one or more candidates observed, none verified;
- `verified`: at least one verified solution;
- `multi_solution`: multiple verified solutions;
- `frontier_populated`: a derived frontier exists for the configured metric tuple.

A collection release must state its exact puzzle coverage and candidate/verified counts.

The existence of a corpus must never be described as exhaustive with respect to all human solutions unless exhaustiveness is demonstrably established.

## 14. Reproducibility

A corpus release manifest must record at least:

- corpus schema version;
- collection identifier and manifest hash;
- build software revision;
- source adapter versions;
- pinned source revisions or immutable object identities;
- source artifact hashes;
- verifier revision/hash;
- normalizer version;
- validation profile version;
- puzzle count;
- candidate solution count;
- verified solution count;
- rejected solution count;
- coverage by puzzle;
- output artifact hashes.

Given the same source cache, manifests, and software revisions, an offline build must reproduce identical canonical row content and release manifest hashes. Byte-for-byte Parquet reproducibility is desirable but must only be promised once the chosen writer/version makes that contract reliable.

## 15. Acquisition versus build

Network acquisition and deterministic materialization are separate operations.

The implemented acquisition boundary is explicit per source:

```text
opus-corpus fetch <collection> --source <source> --cache <path> [--source-root <path>]
```

The existing release shell consumes canonical JSONL projections:

```text
opus-corpus release build <collection> --input <path> --output <path> --payload-policy <policy> [--coverage-policy complete|subset]
```

The remaining production materialization work connects cached source facts, canonical artifacts, verification, and normalization to those release inputs. The local cache is content-addressed; deterministic materialization must consume pinned cached objects rather than mutable remote URLs.

## 16. Testing requirements

Tests exist at three levels.

### Schema and identity tests

- stable canonical IDs;
- alias resolution;
- collection membership;
- schema validation.

### Adapter contract tests

- tiny frozen fixtures per upstream source;
- adapter output conforms to canonical entities;
- repeated imports are idempotent;
- source discrepancies are preserved rather than overwritten.

### Corpus invariants

For a releasable collection:

- every required puzzle has a canonical puzzle identity;
- every included artifact has provenance;
- every `verified` solution has verifier evidence;
- no dangling IDs or hashes exist;
- derived Pareto members are actually nondominated under the declared metric tuple;
- no generated view is hand-maintained;
- repeated pinned builds produce identical canonical manifests.

## 17. v1 non-goals

V1 does not require:

- a database server;
- a custom simulator;
- a semantic-equivalence engine;
- a web service;
- an agent-maintained reconciliation process;
- hand-authored leaderboard snapshots;
- direct mirroring of every upstream repository layout;
- a train/validation/test split before benchmark split methodology is explicitly designed and versioned.

## 18. Release acceptance criteria

A first stable corpus release is complete when:

1. one command can materialize the frozen target collection from permitted/pinned source inputs;
2. every required puzzle in the collection has at least one verifier-successful solution or the release explicitly fails;
3. every published solution is traceable to immutable source evidence;
4. headline metrics are recomputed rather than trusted from source metadata;
5. discrepancies and missing coverage are reported, never repaired manually;
6. generated views are fully reproducible from canonical source facts;
7. an offline rebuild from the pinned content cache reproduces the canonical release manifest;
8. Hugging Face export passes the contract in `hugging-face-export.md`.

## 19. Settled and remaining decisions

Several early design choices are now settled by committed repository state:

- first collection: immutable `base-game-2026-06-16` with 166 puzzle identities;
- canonical puzzle IDs and aliases: committed in the frozen collection inventory;
- implementation toolchain: Python 3.12 with a locked `uv` environment;
- repository-authored material license: MIT, with third-party corpus scope and redistribution policy defined in `RIGHTS.md`;
- schema authority: packaged repository JSON Schemas resolved through `opus_corpus.schema_resources`;
- Parquet implementation: pinned `pyarrow==21.0.0` with `zstd` compression and deterministic logical row ordering;
- release configs: `puzzles`, `solutions`, `observations`, and `normalized`;
- default publication policy: `metadata-only`, with payload inclusion gated by per-artifact rights status;
- benchmark architecture: verifier-backed protocol/collection separation and Solve-first v0.1 scope in `benchmark-protocol.md`.

Remaining decisions that affect stable v1 behavior include:

- source-specific redistribution conclusions where rights remain unresolved;
- exact pinned `omsim` / `libverify` verifier revision and validation-profile identity for v1;
- publication policy for normalized structures derived from local-only bytes;
- final Hugging Face namespace/repository identity and publication credentials/automation policy.

These remaining decisions must be resolved explicitly at the boundary they govern. They must not be inferred from technical availability or silently encoded in generated state.