# Roadmap

This roadmap defines the dependency order from the current corpus factory to a complete, reproducible Opus Magnum research corpus.

It is a strategic map, not a task tracker. GitHub pull requests and issues are the live execution surface, while [`TODO.md`](TODO.md) carries the coarse current packet/dependency snapshot. Coverage counts, generated manifests, verification results, and other derivable state belong in deterministic software outputs rather than this document.

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

The repository has the durable outer structure and canonical middle needed by the roadmap:

- the immutable 166-puzzle `base-game-2026-06-16` collection;
- canonical collection and release schemas packaged as repository resources;
- explicit complete/subset coverage policy and rights-aware payload policy;
- deterministic release manifests, Parquet materialization, validation, staging, and publication machinery;
- a single content-addressed acquisition cache with immutable provenance receipts;
- one authoritative exact-byte `ContentStore` shared by acquisition and canonical artifact materialization;
- deterministic content-derived artifact identity, exact-byte deduplication, provenance preservation, conservative rights folding, and fail-closed artifact conflicts;
- pinned `om-archive`, `om-leaderboard`, `omsim`, and molecule-db acquisition plus an explicit local `official-game` path;
- canonical `SolutionArtifact`, `Observation`, and `PuzzleArtifact` materialization from cached source facts;
- deterministic puzzle-artifact coverage derivation and fail-closed ambiguity handling;
- a canonical `Verification` contract and pinned deterministic `omsim` / `libverify` implementation;
- deterministic artifact-to-verification materialization with recomputed authoritative metrics and structured failure retention;
- a strict normalized-solution contract plus deterministic `.solution` parser and `SolutionNormalizer` implementation;
- normalized-puzzle and deterministic serialization seams;
- a documented benchmark protocol boundary for future research-grade evaluation.

The remaining v1 work is downstream integration: deterministically project those canonical entities into the existing release inputs, then run the complete frozen-collection release path and satisfy its coverage/publication acceptance criteria.

## Milestone 1: Canonical verification and solution-normalization contracts

**Status:** landed.

**Goal:** Fix canonical verification and normalized-solution boundaries independently from parser- or simulator-specific implementations.

Exit criteria are satisfied: verification and normalization identities are deterministic, their schemas are strict, implementation seams are explicit, and serialization remains a downstream projection rather than another authority.

## Milestone 2: Canonical artifact materialization

**Status:** landed.

**Goal:** Convert acquired source facts into the canonical artifact/provenance model without introducing a second storage mechanism.

Cached source bytes now materialize deterministically as `PuzzleArtifact` and `SolutionArtifact` records, source sightings/metadata materialize as `Observation` records, and artifact IDs remain content-derived. Exact-byte SHA-256 identity is the v1 deduplication boundary, multiple sources preserve multiple provenance facts, rights are folded conservatively, and identity/format/corruption conflicts fail closed through the shared content store.

## Milestone 3: Authoritative puzzle-definition acquisition

**Status:** acquisition and canonical puzzle-artifact materialization landed; complete collection coverage is a release-boundary criterion.

**Goal:** Provide verifier-ready puzzle artifacts while keeping exact bytes distinct from semantic problem evidence.

The `omsim`, molecule-db, and local official-byte acquisition paths are implemented and feed the canonical `PuzzleArtifact` materialization path. Semantic evidence is not treated as proof of exact official bytes, and verifier-usable artifacts retain explicit provenance, format, hash, and rights status. Any remaining missing complete-collection coverage is reported mechanically during the release path rather than solved by adding another source-storage mechanism.

## Milestone 4: Deterministic verification

**Status:** landed.

**Goal:** Make verifier results, not source claims, authoritative for executable validity and computed metrics.

The pinned `omsim` / `libverify` implementation is connected through the `Verifier` protocol. Canonical verification recomputes cost, cycles, area, and instructions, retains parse/simulation failures as structured data, preserves source-declared observations independently, versions verifier/profile identity, and is deterministic for identical canonical artifacts plus pinned verifier inputs.

## Milestone 5: Normalization and deterministic corpus materialization

**Status:** parser/normalizer landed; release materialization is the active remaining slice.

**Goal:** Close the gap between canonical artifacts/verifications and the release factory.

The deterministic `.solution` parser and `SolutionNormalizer` are implemented. Normalized solution records retain exact `SolutionArtifact` lineage and normalizer identity, while normalization failure remains independent from verification truth.

Remaining milestone exit criteria:

- generate canonical puzzle, solution, observation, verification-derived, and normalized release rows from the existing canonical entities;
- feed the current release builder without creating a second corpus or row authority;
- preserve verification-derived metrics and payload-rights enforcement through the projection;
- prove repeated offline materialization from the same canonical inputs produces identical row content and release manifest hashes.

The tiny fixture corpus may remain hand-authored as a test fixture; it is not production authority.

## Milestone 6: Complete frozen base-game release

**Status:** downstream of release materialization.

**Goal:** Produce and publish the first stable complete corpus for `base-game-2026-06-16`.

Exit criteria:

- one deterministic offline build path materializes the frozen collection from permitted, pinned cached inputs;
- all 166 required puzzles are present;
- every required puzzle has at least one verifier-successful solution, otherwise the complete build fails;
- every published solution is traceable to immutable source evidence;
- headline metrics are recomputed by the pinned verifier rather than trusted from filenames or source metadata;
- missing coverage and source/verifier discrepancies are reported, never manually repaired;
- the release manifest records collection hash, source revisions, artifact hashes, verifier identity, validation profile, normalizer version, derived coverage, and output hashes;
- an offline rebuild from the same content cache reproduces the canonical release manifest;
- rights policy is enforced at publication time;
- Hugging Face export passes [`hugging-face-export.md`](hugging-face-export.md), with publication remaining a downstream projection rather than a new authority.

This milestone is the v1 release boundary.

## Milestone 7: Research-grade derived views and benchmarks

**Status:** protocol drafted; implementation follows the v1 canonical path without becoming an authority.

**Goal:** Turn the canonical corpus into useful benchmark and ML research surfaces without adding hand-maintained datasets.

The benchmark architecture in [`benchmark-protocol.md`](benchmark-protocol.md) separates protocol from collection identity, starts with verifier-backed Solve evaluation, preserves Opus Magnum's multi-objective metrics, and treats public base-game results separately from claims about held-out generalization.

Candidate derived views include all verified solutions, ordinary/vanilla constructible solutions, record-eligible solutions, Pareto frontiers, best-known metric views, human-versus-machine provenance views, benchmark selections, and deterministic model-oriented serializations.

Every such view must be generated from canonical facts by versioned deterministic software. Selection/frontier predicates must be explicit and testable, model-oriented formats remain serializers rather than parallel datasets, and any train/validation/test split requires an explicit leakage-aware methodology.

## Milestone 8: Expand beyond the frozen base game

**Status:** later.

**Goal:** Reuse the same pipeline for additional Opus Magnum problem and solution classes.

Potential collection families include De Re Metallica, other official/special puzzle sets, Workshop/custom puzzles, tournament/community collections, additional historical archives, and clearly identified machine-generated baselines such as OpusSolver output.

Expansion rules:

- express new scope through new immutable collection manifests rather than mutating `base-game-2026-06-16`;
- translate new source facts into the existing canonical model rather than redefining canonical IDs or release schemas;
- keep rights, provenance, validation semantics, and coverage explicit per source/artifact class;
- extend shared deterministic infrastructure only when a genuinely new primitive is required.

## Ordering and parallelism

The dependency spine is:

```text
contracts
  → artifact materialization
  → puzzle definitions
  → verification
  → normalization
  → release materialization
  → complete release
  → research views and collection expansion
```

The first five stages through normalization are landed. Current packet state and concurrency boundaries live in [`TODO.md`](TODO.md), avoiding duplicated fast-moving status here.

Independent source adapters or research experiments may advance in parallel only when they consume existing authoritative primitives and do not create alternate caches, artifact stores, reconciliation systems, or hand-maintained projections.

## Decision rules

When choosing implementation work, prefer the option that preserves these invariants:

1. **One authoritative path.** Reuse existing acquisition, storage, canonicalization, verification, normalization, and release primitives before adding another mechanism.
2. **Software derives state.** Repeated bookkeeping, reconciliation, counting, materialization, and known recovery behavior belong in deterministic software.
3. **Reasoning is for judgment work.** Use reasoning for research, design, synthesis, and novel implementation, not maintenance of generated indexes or status projections.
4. **Fail closed.** Unknown puzzle fields, ambiguous identities, corrupt cached objects, verifier failures, and rights uncertainty remain explicit rather than silently repaired.
5. **Preserve evidence.** Source claims and verifier-derived facts may disagree; both are retained with distinct provenance.
6. **Keep rights orthogonal to metadata utility.** Restricted raw bytes do not prevent provenance, hashes, verified metrics, or other permitted derived facts from being published.
7. **Defer semantic deduplication.** V1 deduplicates exact bytes only. Machine-equivalence or symmetry clustering requires a separately specified derived algorithm.

## V1 definition of done

The roadmap reaches v1 when the release acceptance criteria in [`dataset-spec.md`](dataset-spec.md) are satisfied for `base-game-2026-06-16`: a complete verifier-backed, provenance-preserving, reproducible corpus can be rebuilt offline from pinned cached facts and exported through the existing release pipeline without manual corpus maintenance.
