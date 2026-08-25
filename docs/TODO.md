# Work topology

This document records stable dependency and concurrency boundaries for repository work. It is not a status board, completion ledger, or assignee system.

Live execution state, ownership, review, and acceptance evidence belong in GitHub issues and pull requests. A merge, closure, reopening, or restack should not require updating this file. Small, understood maintenance that does not merit independent coordination lives in [`CLEANUP.md`](CLEANUP.md).

Use this topology to answer two questions: **what depends on what, and which capability boundaries can change independently?**

## Core corpus dependency graph

```text
WP-01 Verification contract ───────────────────────────────┐
                                                          │
WP-03 Artifact materializer ─→ WP-04 Solution/Observation ├→ WP-09 Verification ───────┐
                                                          │                             │
WP-05 omsim puzzle source ───────┐                         │                             │
WP-06 molecule-db semantic source ├→ WP-08 PuzzleArtifact ┘                             ├→ WP-11 Release materialization → WP-12 Complete v1 release
WP-07 official/local puzzle bytes ┘                                                       │
                                                                                        │
WP-02 Normalized-solution contract ─┐                                                   │
WP-04 Solution/Observation ──────────┴→ WP-10 Solution parsing/normalization ────────────┘
```

The graph is about interface dependencies, not present-tense status. Inspect GitHub before starting work on any packet or neighboring surface.

## Research dependency graph

```text
canonical puzzle / verification / release primitives
        ├→ WP-13 deterministic puzzle serializer ─────┐
        ├→ WP-14 verifier-derived reference views ────┼→ research and comparison surfaces
        └→ WP-15 benchmark result/report model ───────┘

WP-13 + WP-15 + pinned verifier ─→ WP-16 v0.1 Solve harness
WP-14 reference metrics/frontiers ─→ optional benchmark comparisons
```

WP-13, WP-14, and WP-15 own separate derived surfaces and may proceed independently when their concrete changes do not overlap. WP-16 is the integration boundary for model execution and deterministic reporting.

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
| **WP-08 PuzzleArtifact coverage/materialization** | WP-03, WP-05, WP-06, WP-07 | Cached puzzle evidence to canonical puzzle artifacts plus derived artifact coverage. |
| **WP-09 Verification implementation** | WP-01, WP-04, WP-08 | Pinned `omsim`/`libverify` verification behind the `Verifier` contract. |
| **WP-10 Solution parser + normalizer** | WP-02, WP-04 | Deterministic `.solution` parsing and normalized-solution materialization. |
| **WP-11 Release materialization** | WP-04, WP-08, WP-09, WP-10 | Canonical facts to the existing release inputs without a second row authority. |
| **WP-12 Complete v1 release** | WP-11 | Complete frozen-collection build, deterministic replay, rights enforcement, and publication acceptance. |
| **WP-13 Deterministic puzzle serializer** | normalized-puzzle and serialization seams | Versioned model-oriented serialization over canonical puzzle semantics. |
| **WP-14 Verifier-derived reference views** | canonical verification/release facts | Deterministic verified, constructibility, eligibility, best-known, and frontier views. |
| **WP-15 Benchmark result model** | benchmark protocol, canonical hashing/schema primitives | Stable attempt/result identities, outcome taxonomy, and deterministic aggregation. |
| **WP-16 v0.1 Solve harness** | WP-13, WP-15, pinned verifier; WP-14 for reference comparisons | Exact-artifact model execution, candidate handling, verification, and reproducible reports. |

## Coordination rules

1. Inspect open GitHub issues and pull requests before changing a packet or adjacent implementation surface.
2. Consume established interfaces rather than recreating acquisition, content storage, schema, verification, normalization, or release mechanisms.
3. Branch from the dependency state the work actually requires. Stack changes only for a real dependency or deliberate collision-avoidance sequence.
4. Own one capability boundary. If a change alters a neighboring public contract, split or restack it instead of silently widening scope.
5. When two items unexpectedly collide, factor the smallest shared primitive or correct the dependency boundary rather than maintaining parallel implementations.
6. Keep repeated bookkeeping, reconciliation, counting, validation, materialization, and known recovery behavior in deterministic software.
7. Treat generated coverage, manifests, views, reports, and publication artifacts as projections, never hand-maintained repository authority.
8. Keep source evidence and verifier-derived facts distinct, preserve disagreement, and fail closed on ambiguity, corruption, unsafe paths, incomplete required coverage, or rights uncertainty.

## Strategic boundaries

The v1 boundary is a complete `base-game-2026-06-16` release that can be reproduced offline from pinned cached facts, has immutable provenance and verifier-backed coverage, enforces rights policy, and passes the Hugging Face export contract.

Research views and benchmarks remain derived from the same canonical facts. They must not become separately curated datasets, hand-maintained leaderboards, or alternate stores. Additional collections should be introduced as new immutable collection definitions that reuse the existing pipeline unless a genuinely new source class proves a new primitive is required.
