# Roadmap

This roadmap defines the dependency order from the current corpus factory to a complete, reproducible Opus Magnum research corpus.

It is a strategic map, not a task tracker. GitHub pull requests and issues are the live execution surface. Coverage counts, generated manifests, verification results, and other derivable state belong in deterministic software outputs rather than this document.

The first target is a stable release of the frozen `base-game-2026-06-16` collection. Broader collections and research views follow from the same canonical pipeline.

## Architectural path

```text
frozen collection definitions
        ↓
pinned source acquisition
        ↓
content-addressed source cache + provenance receipts
        ↓
canonical PuzzleArtifact / SolutionArtifact / Observation records
        ↓
PuzzleArtifact + SolutionArtifact verification
        ↓
normalized representations and deterministic derived views
        ↓
canonical release rows
        ↓
validated Parquet + manifest + dataset card
        ↓
Hugging Face and other downstream projections
```

Each layer has one authority. Upstream sources provide immutable facts, repository software derives canonical and generated state, and publication surfaces remain projections.

## Foundation already established

The repository already has the durable outer structure needed by the roadmap:

- the immutable 166-puzzle `base-game-2026-06-16` collection;
- canonical collection and release schemas packaged as repository resources;
- explicit complete/subset coverage policy;
- rights-aware payload policy;
- deterministic release manifests, Parquet materialization, validation, staging, and publication machinery;
- a single content-addressed acquisition cache with immutable provenance receipts;
- one authoritative exact-byte `ContentStore` shared by acquisition and canonical artifact materialization;
- deterministic content-derived artifact identity, exact-byte deduplication, provenance preservation, conservative rights folding, and fail-closed artifact conflicts from PR #15;
- pinned `om-archive` and `om-leaderboard` acquisition;
- pinned `omsim` campaign puzzle-definition acquisition;
- pinned `molecule-db` semantic acquisition and topology reconciliation;
- an explicit local `official-game` path for exact official `.puzzle` bytes;
- source-adapter contracts with fail-closed unimplemented sources;
- a canonical Verification contract and simulator-independent `Verifier` seam;
- a strict normalized-solution contract and parser-independent `SolutionNormalizer` seam;
- normalized-puzzle and deterministic serialization seams;
- a documented benchmark protocol boundary for future research-grade evaluation.

The remaining work is primarily the source-specific canonical middle between the shared artifact/provenance core and the existing release factory.

## Milestone 1: Canonical verification and solution-normalization contracts

**Status:** landed.

**Goal:** Fix the boundaries before connecting parser- or simulator-specific implementations.

Exit criteria:

- `Verification` is a first-class canonical derived entity with a strict schema.
- Verification identity is deterministic from the exact puzzle artifact, solution artifact, verifier identity, and validation profile.
- A simulator-independent `Verifier` protocol defines the implementation seam.
- The normalized-solution schema strictly represents parts, tracks, programs, instructions, and deterministic summaries.
- Normalized-solution identity and normalizer versioning are deterministic.
- A parser-independent `SolutionNormalizer` protocol defines the normalization seam.
- Serialization remains a downstream projection over normalized records rather than another authority.

No `.solution` parser or `omsim` integration is required to exit this milestone.

## Milestone 2: Canonical artifact materialization

**Status:** shared core landed; source-specific solution/observation and puzzle-artifact materialization remain.

**Goal:** Convert acquired source facts into the canonical artifact/provenance model without introducing a second storage mechanism.

The shared core of this milestone landed in PR #15. Acquisition and materialization now share one exact-byte `ContentStore`; receipt-based ingestion provides deterministic content-derived identity, exact-byte deduplication with multi-source provenance, conservative artifact-rights aggregation, and fail-closed integrity/identity/format handling. The remaining milestone work is source-specific orchestration and projection into concrete `SolutionArtifact`, `Observation`, and verifier-usable `PuzzleArtifact` records in WP-04 and WP-08.

Exit criteria:

- Cached source bytes can be deterministically materialized as `PuzzleArtifact` and `SolutionArtifact` records.
- Source sightings and metadata are materialized as `Observation` records.
- Artifact IDs are content-derived and stable.
- Exact-byte SHA-256 identity is the only v1 deduplication boundary.
- Multiple sources observing the same exact artifact preserve multiple observations rather than duplicate artifacts.
- Rights status is conservatively aggregated without granting permissions not established by source evidence.
- Puzzle-ID, format, source-mutation, and corrupt-object conflicts fail closed.
- Acquisition and canonical materialization reuse the existing content-addressed cache/object primitive. No parallel object store, snapshot authority, or alternate ingestion path is introduced.

## Milestone 3: Authoritative puzzle-definition acquisition

**Status:** acquisition sources landed; complete verifier-usable `PuzzleArtifact` coverage remains.

**Goal:** Provide verifier-ready puzzle artifacts for the complete frozen collection while keeping exact bytes distinct from semantic problem evidence.

The `omsim`, `molecule-db`, and local official-byte acquisition paths are implemented. This milestone now depends on deterministic canonical puzzle-artifact materialization and coverage resolution rather than additional source-specific storage mechanisms.

Exit criteria:

- Puzzle-definition adapters consume pinned or locally acquired source facts through the existing acquisition/cache boundary.
- `omsim` campaign fixtures, locally acquired official puzzle bytes, and independent semantic evidence are represented according to their actual evidentiary role.
- Semantic evidence such as molecule topology is not treated as proof of exact official `.puzzle` byte identity.
- Every puzzle artifact used for verification has explicit provenance, format, hash, and rights status.
- The pipeline reports deterministic puzzle-artifact coverage and fails rather than inventing unknown game fields.
- A complete base-game build can resolve at least one verifier-usable `PuzzleArtifact` for every required puzzle.

## Milestone 4: Deterministic verification

**Goal:** Make verifier results, not source claims, authoritative for executable validity and computed metrics.

Exit criteria:

- A pinned `omsim`/`libverify` implementation is connected through the `Verifier` protocol.
- Puzzle and solution parsing, simulation, and metric extraction produce canonical `Verification` records.
- Successful verification records at least cost, cycles, area, and instructions.
- Parse failures, simulator failures, and structured verifier errors are retained as data rather than discarded.
- Source-declared scores remain observations and can disagree with recomputed metrics without overwriting either fact.
- Validation-profile identity is versioned and distinct predicates such as simulator-valid, ordinary constructible, and record-eligible remain separate.
- Re-running verification against identical cached artifacts and pinned verifier inputs produces identical canonical results.

## Milestone 5: Normalization and deterministic corpus materialization

**Goal:** Close the gap between canonical artifacts/verifications and the release factory.

Exit criteria:

- A deterministic `.solution` parser feeds the `SolutionNormalizer` implementation.
- Normalized solution records identify the exact source `SolutionArtifact` and record the normalizer version.
- Normalized puzzle records continue to identify the exact source `PuzzleArtifact`.
- Normalization failure does not invalidate a successfully verified raw artifact.
- Canonical puzzle, solution, observation, verification-derived, and normalized release rows are generated from source facts and pinned software rather than hand-authored for production builds.
- Production materialization consumes the existing canonical entities and feeds the current release builder without creating a second corpus authority.
- Repeated offline materialization from the same cache and revisions produces identical canonical row content and manifest hashes.

The tiny fixture corpus may remain hand-authored as a test fixture; it is not production authority.

## Milestone 6: Complete frozen base-game release

**Goal:** Produce and publish the first stable complete corpus for `base-game-2026-06-16`.

Exit criteria:

- One deterministic offline build path materializes the frozen collection from permitted, pinned cached inputs.
- All 166 required puzzles are present.
- Every required puzzle has at least one verifier-successful solution; otherwise the complete build fails.
- Every published solution is traceable to immutable source evidence.
- Headline metrics are recomputed by the pinned verifier rather than trusted from filenames or source metadata.
- Missing coverage and source/verifier discrepancies are reported, never manually repaired.
- The release manifest records the collection hash, source revisions, artifact hashes, verifier identity, validation profile, normalizer version, derived coverage, and output hashes.
- An offline rebuild from the same content cache reproduces the canonical release manifest.
- Rights policy is enforced at publication time; metadata-only publication remains valid when raw bytes are not redistributable.
- Hugging Face export passes `docs/hugging-face-export.md` and the release is published as a downstream projection, not a new authority.

This milestone is the v1 release boundary.

## Milestone 7: Research-grade derived views and benchmarks

**Goal:** Turn the canonical corpus into useful benchmark and ML research surfaces without adding hand-maintained datasets.

The benchmark architecture is now drafted in [`benchmark-protocol.md`](benchmark-protocol.md). It separates protocol from collection identity, starts with verifier-backed Solve evaluation, preserves Opus Magnum's multi-objective metrics, and treats public base-game results separately from claims about held-out generalization.

Candidate derived views include:

- all verified solutions;
- ordinary/vanilla constructible solutions;
- record-eligible solutions;
- Pareto frontiers over declared metric tuples;
- best cost, cycles, area, and instructions;
- human-observed versus machine-generated solution views;
- one-per-puzzle benchmark selections;
- normalized puzzle and solution representations for model training;
- deterministic model-oriented serialization formats derived from normalized records.

Benchmark work should begin with the narrow v0.1 scope in `benchmark-protocol.md`: Solve, one-shot plus one bounded interactive profile, a deterministic normalized-puzzle serialization, exact verifier-backed correctness, explicit failure taxonomy, and multi-objective quality reporting.

Exit criteria:

- Each view is generated from canonical facts by versioned deterministic software.
- Selection and frontier predicates are explicit and testable.
- No view is maintained by agents or manual bookkeeping.
- Model-oriented text or token formats remain serializers over normalized records, not parallel canonical datasets.
- Benchmark protocol, collection, serializer, verifier, attempt policy, and reporting identity are all explicit.
- Benchmark train/validation/test splits are added only after an explicit leakage-aware methodology is designed and versioned.

## Milestone 8: Expand beyond the frozen base game

**Goal:** Reuse the same pipeline for additional Opus Magnum problem and solution classes.

Potential collection families include:

- De Re Metallica;
- official production or special puzzle sets not in the first collection;
- Workshop/custom puzzles;
- tournament and community collections;
- additional historical archives;
- clearly identified machine-generated baselines such as OpusSolver output.

Expansion rules:

- New scope is expressed through new immutable collection manifests rather than mutating `base-game-2026-06-16`.
- New adapters translate source facts into the existing canonical model; they do not redefine canonical IDs or release schemas.
- Rights, provenance, validation semantics, and coverage remain explicit per source and artifact class.
- Shared deterministic infrastructure is extended only when a genuinely new primitive is required.

## Ordering and parallelism

The dependency spine is:

```text
contracts
  → artifact materialization
  → puzzle definitions
  → verification
  → normalization/materialization
  → complete release
  → research views and collection expansion
```

Independent source adapters may advance in parallel when they consume the existing acquisition primitives. They must not create alternate caches, artifact stores, reconciliation systems, or hand-maintained projections.

Likewise, research on normalized representations and benchmark serializers may proceed before the complete release, but no experimental representation becomes an authority or blocks verifier-backed canonical materialization.

## Decision rules

When choosing implementation work, prefer the option that preserves these invariants:

1. **One authoritative path.** Reuse existing acquisition, storage, canonicalization, verification, and release primitives before adding another mechanism.
2. **Software derives state.** Repeated bookkeeping, reconciliation, counting, materialization, and known recovery behavior belong in deterministic software.
3. **Reasoning is for judgment work.** Use reasoning for research, design, synthesis, and novel implementation, not maintenance of generated indexes or status projections.
4. **Fail closed.** Unknown puzzle fields, ambiguous identities, corrupt cached objects, verifier failures, and rights uncertainty remain explicit rather than silently repaired.
5. **Preserve evidence.** Source claims and verifier-derived facts may disagree; both are retained with distinct provenance.
6. **Keep rights orthogonal to metadata utility.** Restricted raw bytes do not prevent provenance, hashes, verified metrics, or other permitted derived facts from being published.
7. **Defer semantic deduplication.** V1 deduplicates exact bytes only. Machine-equivalence or symmetry clustering requires a separately specified derived algorithm.

## V1 definition of done

The roadmap reaches v1 when the release acceptance criteria in `docs/dataset-spec.md` are satisfied for `base-game-2026-06-16`: a complete verifier-backed, provenance-preserving, reproducible corpus can be rebuilt offline from pinned cached facts and exported through the existing release pipeline without manual corpus maintenance.
