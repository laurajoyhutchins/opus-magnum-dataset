# Work topology

This document records stable dependency and concurrency boundaries for repository work. It is not a status board, completion ledger, or assignee system.

Live execution state, ownership, review, and acceptance evidence belong in GitHub issues and pull requests. A merge, closure, reopening, or restack should not require updating this file. Small, understood maintenance that does not merit independent coordination lives in [`CLEANUP.md`](CLEANUP.md).

Use this topology to answer two questions: **what depends on what, and which capability boundaries can change independently?**

## Core corpus dependency graph

```text
WP-01 Verification contract ──────────────────────────────────────────────────┐
                                                                              │
WP-03 Artifact materializer ─→ WP-04 SolutionArtifact + Observation ──────────┤
                                                                              │
WP-05 omsim puzzle source ─────────┐                                           │
WP-06 molecule-db semantic source ─┼→ WP-08 PuzzleDefinition / PuzzleArtifact ├→ WP-09 Verification ───────┐
WP-07 official/local puzzle bytes ─┘                                           │                             │
                                                                                                            ├→ WP-11 Release materialization → WP-12 Complete v1 release
WP-02 Normalized-solution contract ─┐                                                                       │
WP-04 SolutionArtifact + Observation ┴→ WP-10 Solution parsing/normalization ───────────────────────────────┘
```

`PuzzleDefinition` is the canonical semantic puzzle boundary. `PuzzleArtifact` remains exact-byte provenance and verifier input. Semantic, artifact, and verifier-ready coverage are derived separately rather than collapsed into one possession flag.

The graph is about interface dependencies, not present-tense status. Inspect GitHub before starting work on any packet or neighboring surface.

## Research dependency graph

```text
canonical semantic puzzle / verification / release primitives
        ├→ WP-13 deterministic puzzle serializer ───────────────┐
        ├→ WP-14 verifier-derived reference views ──────────────┤
        └→ WP-15 benchmark result/report model ─────────────────┤
                                                                │
deterministic candidate-output compiler ────────────────────────┤→ WP-16 v0.1 Solve harness
                                                                │
derived verifier-ready benchmark inventory ─────────────────────┘

WP-14 reference metrics/frontiers ─→ optional benchmark comparisons
```

WP-13, WP-14, and WP-15 own separate derived surfaces. Candidate-output compilation and benchmark eligibility are deterministic supporting boundaries for WP-16 and should not be reimplemented in runner prompts or harness-local bookkeeping. WP-16 is the integration boundary for model execution and deterministic reporting.

## Packet boundaries

| Packet | Depends on | Owns |
| --- | --- | --- |
| **WP-01 Verification contract** | canonical artifact concepts | Strict `Verification` schema, identity, and simulator-independent protocol. |
| **WP-02 Normalized-solution contract** | WP-01 domain separation | Strict normalized-solution schema, deterministic identity, and `SolutionNormalizer` seam. |
| **WP-03 Artifact materializer core** | acquisition cache/content primitives | Shared exact-byte artifact/provenance materialization and identity. |
| **WP-04 SolutionArtifact + Observation materialization** | WP-03 | Cached solution/metadata facts to canonical solution artifacts and observations. |
| **WP-05 omsim puzzle source** | acquisition/cache primitives | Pinned `omsim` puzzle-source acquisition. |
| **WP-06 molecule-db semantic source** | acquisition/cache primitives | Pinned semantic puzzle evidence and reconciliation. |
| **WP-07 Official/local puzzle-byte path** | acquisition/cache primitives | Explicit local exact official puzzle-byte acquisition and provenance. |
| **WP-08 Puzzle evidence materialization** | WP-03, WP-05, WP-06, WP-07 | Cached puzzle evidence to canonical `PuzzleDefinition` and `PuzzleArtifact` records plus distinct semantic, artifact, and verifier-ready coverage. |
| **WP-09 Verification implementation** | WP-01, WP-04, verifier-ready PuzzleArtifact coverage | Pinned `omsim`/`libverify` verification behind the `Verifier` contract. |
| **WP-10 Solution parser + normalizer** | WP-02, WP-04 | Deterministic `.solution` parsing and normalized-solution materialization. |
| **WP-11 Release materialization** | canonical PuzzleDefinition facts, WP-04, WP-09, WP-10 | Canonical semantic puzzle, solution, observation, verification-derived, and normalized facts to the existing release inputs without a second row authority. |
| **WP-12 Complete v1 release** | WP-11, complete verifier-ready artifact coverage | Complete frozen-collection build, deterministic replay, rights enforcement, and publication acceptance. |
| **WP-13 Deterministic puzzle serializer** | canonical `PuzzleDefinition` and serialization seam | Versioned model-oriented serialization over canonical puzzle semantics. |
| **WP-14 Verifier-derived reference views** | canonical verification/release facts | Deterministic verified, constructibility, eligibility, best-known, and frontier views. |
| **WP-15 Benchmark result model** | benchmark protocol, canonical hashing/schema primitives | Stable attempt/result identities, outcome taxonomy, and deterministic aggregation. |
| **WP-16 v0.1 Solve harness** | WP-13, WP-15, deterministic candidate-output compiler, derived verifier-ready benchmark inventory, pinned verifier; WP-14 for optional reference comparisons | Semantic model input, candidate handling, exact-artifact verification, and reproducible reports. |

## Coordination rules

1. Inspect open GitHub issues and pull requests before changing a packet or adjacent implementation surface.
2. Consume established interfaces rather than recreating acquisition, content storage, schema, verification, normalization, or release mechanisms.
3. Branch from the dependency state the work actually requires. Stack changes only for a real dependency or deliberate collision-avoidance sequence.
4. Own one capability boundary. If a change alters a neighboring public contract, split or restack it instead of silently widening scope.
5. When two items unexpectedly collide, factor the smallest shared primitive or correct the dependency boundary rather than maintaining parallel implementations.
6. Keep repeated bookkeeping, reconciliation, counting, validation, materialization, and known recovery behavior in deterministic software.
7. Treat generated coverage, executable benchmark inventories, manifests, views, reports, and publication artifacts as projections, never hand-maintained repository authority.
8. Keep semantic puzzle definitions, exact artifact evidence, source observations, and verifier-derived facts distinct; preserve disagreement and fail closed on ambiguity, corruption, unsafe paths, incomplete required coverage, or rights uncertainty.

## Strategic boundaries

The v1 boundary is a complete `base-game-2026-06-16` release that can be reproduced offline from pinned cached facts, has immutable provenance and verifier-backed coverage, enforces rights policy, and passes the Hugging Face export contract.

Research views and benchmarks remain derived from the same canonical facts. They must not become separately curated datasets, hand-maintained leaderboards, alternate stores, or prompt-maintained eligibility lists. Additional collections should be introduced as new immutable collection definitions that reuse the existing pipeline unless a genuinely new source class proves a new primitive is required.
