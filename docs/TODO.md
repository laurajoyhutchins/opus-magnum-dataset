# TODO

This checklist translates the strategic [`roadmap.md`](roadmap.md) into concrete implementation slices.

It is not a second issue tracker. GitHub issues and pull requests are the live execution record. This file records dependency order, ownership boundaries, and a coarse landed / in-review / blocked snapshot. Generated coverage, verification counts, manifests, benchmark results, and other derivable facts belong in deterministic software outputs rather than hand-maintained entries here.

Use this file to answer two questions: **what can be worked on concurrently without overlapping ownership, and what should we build next?**

## Work graph

```text
[LANDED] WP-01 Verification contract (#13)
        │
        └──────────────→ [LANDED] WP-02 Normalized-solution contract (#14)

[LANDED] WP-03 Artifact materializer core (#15)
        │
        └────→ [IN REVIEW] WP-04 SolutionArtifact + Observation materialization (#30) ─┐
                                                                                       │
[LANDED] WP-05 omsim puzzle source (#19) ─────┐                                        │
[LANDED] WP-06 molecule-db semantic source (#18) ├→ [IN REVIEW] WP-08 PuzzleArtifact (#31)
[LANDED] WP-07 official/local puzzle-byte path (#16) ┘ coverage/materialization        │
                                                       │                               │
[LANDED] WP-01 ───────────────────────────────────────┼──────┐                        │
                                                       ↓      │                        │
                                                 WP-09 Verification ←──────────────────┘
                                                       │
[LANDED] WP-02 ─────────────────────────┐              │
WP-04 ──────────────────────────────────┴→ WP-10 Solution parser + normalizer
                                                       │
WP-04 ────────────────────────────────────────────────┐
WP-08 ────────────────────────────────────────────────┤
WP-09 ────────────────────────────────────────────────┼→ WP-11 Release materialization
WP-10 ────────────────────────────────────────────────┘
                                                       │
                                                       ↓
                                               WP-12 Complete v1 release
```

The active architectural lanes are WP-04 in PR #30 and WP-08 in PR #31. They are independent enough to review and land separately. WP-09 and WP-10 remain blocked on their declared upstream packets; WP-11 and WP-12 remain downstream of those implementations.

Release-boundary hardening #20, #21, #22, and #23 has landed through PRs #24, #29, #26, and #25 respectively. The repository-wide MIT license and third-party corpus rights boundary landed in PR #32.

## Landed foundations

These capabilities already exist and should be consumed rather than recreated:

- [x] Frozen 166-puzzle `base-game-2026-06-16` collection and collection validation.
- [x] Four-config deterministic release shell with Parquet, manifest, dataset card, staging, and publication guards.
- [x] Explicit `complete` / `subset` coverage policy with mechanically derived per-puzzle release coverage.
- [x] Rights-aware payload policy with repository-wide policy in [`../RIGHTS.md`](../RIGHTS.md).
- [x] MIT license for repository-authored project material without relicensing third-party corpus payloads.
- [x] Content-addressed acquisition cache with immutable receipts and source-mutation protection.
- [x] One authoritative exact-byte `ContentStore` shared by acquisition and materialization.
- [x] Receipt-only canonical artifact/provenance materializer with deterministic exact-byte identity, deduplication, provenance preservation, conservative rights folding, and fail-closed conflicts.
- [x] Pinned `om-archive` and `om-leaderboard` acquisition.
- [x] Pinned `omsim` campaign puzzle-definition acquisition.
- [x] Pinned molecule-db semantic acquisition and topology reconciliation.
- [x] Explicit local official `.puzzle` acquisition with immutable manifest provenance and `local_fetch_only` rights.
- [x] Canonical `Verification` contract and simulator-independent `Verifier` seam.
- [x] Strict normalized-solution contract and `SolutionNormalizer` seam.
- [x] Normalized-puzzle schema, exact `PuzzleArtifact` lineage, and deterministic serialization seam.
- [x] Package-native authoritative JSON Schemas that work from editable installs and installed wheels.
- [x] Release staging overlap protection, manifest path confinement, and unsupported manifest-version rejection.
- [x] Draft benchmark protocol specifying verifier-backed Solve evaluation and reproducible benchmark identity.

## Work packets

Each packet owns one capability. Before starting work, inspect open issues and pull requests and avoid overlapping an active implementation surface.

| Packet | State | Depends on | Owns | Complete when |
| --- | --- | --- | --- | --- |
| **WP-01 Verification contract** | **Settled** | current `main` at implementation time | Canonical `Verification` schema, identity, protocol, contract tests | PR #13 merged with contract tests green |
| **WP-02 Normalized-solution contract** | **Settled** | WP-01 | Strict normalized-solution schema, deterministic identity, `SolutionNormalizer` seam | PR #14 merged with contract tests green |
| **WP-03 Artifact materializer core** | **Settled** | landed content-addressed cache | Shared canonical artifact/provenance materialization primitive | PR #15 merged with integrity, conflict, determinism, provenance, and local-root tests green |
| **WP-04 SolutionArtifact + Observation materialization** | **In review: PR #30** | WP-03 | Cached solution/metadata facts → canonical `SolutionArtifact` + `Observation` records | overlapping exact bytes dedupe while observations, metadata-only observations, and source claims remain preserved |
| **WP-05 omsim puzzle source** | **Settled** | acquisition/cache primitives | Pinned `omsim` campaign puzzle acquisition | PR #19 merged with deterministic/idempotent rights-aware acquisition tests green |
| **WP-06 molecule-db semantic source** | **Settled** | acquisition/cache primitives | Pinned molecule-db semantic acquisition | PR #18 plus hardening PR #27 landed with evidence retention and upstream reconciliation tests green |
| **WP-07 Official/local puzzle-byte path** | **Settled** | acquisition/cache primitives | Explicit local exact official puzzle-byte acquisition | PR #16 merged with provenance, rights, portability, and fail-closed regressions green |
| **WP-08 PuzzleArtifact coverage/materialization** | **In review: PR #31** | WP-03, WP-05, WP-06, WP-07 | Cached puzzle facts/evidence → canonical `PuzzleArtifact` records + derived coverage | every required puzzle resolves deterministically to verifier-usable exact-byte evidence or coverage fails explicitly |
| **WP-09 Verification implementation** | Blocked | WP-01, WP-04, WP-08 | Pinned `omsim` / `libverify` implementation behind `Verifier` | parse/simulation success and failure retained; metrics recomputed; repeated evaluation deterministic |
| **WP-10 Solution parser + normalizer** | Blocked | WP-02, WP-04 | Deterministic `.solution` parser and `SolutionNormalizer` implementation | normalized records retain exact artifact lineage/version and normalization does not alter verification facts |
| **WP-11 Release materialization** | Blocked | WP-04, WP-08, WP-09, WP-10 | Canonical entities → existing four release inputs | repeated offline materialization yields identical canonical rows/manifest hashes and release validation passes |
| **WP-12 Complete v1 release** | Blocked | WP-11 | Full frozen-collection build and publication readiness | all 166 puzzles have verifier-successful coverage, offline rebuild reproduces the canonical manifest, and HF contract passes |

## Contribution coordination

1. Inspect open issues and pull requests before starting an open packet. Use ordinary GitHub mechanisms for live coordination; no external claim service is required.
2. Consume settled interfaces from `main` rather than reopening completed architectural work by default.
3. Avoid concurrent work on the same implementation surface unless the dependency graph explicitly requires a stack.
4. Branch from the settled dependency base. Stack only when there is a real dependency or deliberate collision-avoidance sequence.
5. Own the declared capability, not neighboring machinery. Split or restack work that requires changing another packet's public contract.
6. Reuse existing acquisition, storage, schema, verification, normalization, and release primitives. Do not create parallel authorities.
7. Keep PR dependencies and non-goals explicit enough that another contributor can work safely beside the change.
8. Consider work complete only with fresh deterministic evidence for its acceptance criteria.
9. If two items unexpectedly collide, fix the graph or factor a smaller shared primitive rather than allowing both branches to mutate the same boundary independently.

## Now

- [ ] Review and land WP-04 in PR #30.
- [ ] Review and land WP-08 in PR #31.
- [x] Land issue #20 staging source/destination overlap protection via PR #24.
- [x] Land issue #21 release-manifest path confinement via PR #29.
- [x] Land issue #22 package-native schema resolution via PR #26.
- [x] Land issue #23 unsupported release-manifest version rejection via PR #25.
- [x] Define repository MIT license scope and third-party corpus rights policy via PR #32.
- [x] Draft the benchmark protocol in [`benchmark-protocol.md`](benchmark-protocol.md).

## Next

### WP-09: deterministic verification

- [ ] Pin the verifier implementation/revision and validation-profile identity used for v1.
- [ ] Implement the `Verifier` protocol using `omsim` / `libverify`.
- [ ] Parse exact puzzle and solution artifacts through the verification path.
- [ ] Emit canonical `Verification` records for successful and failed attempts.
- [ ] Recompute at least cost, cycles, area, and instructions for successful verifications.
- [ ] Preserve structured parse and simulation failures as canonical data.
- [ ] Keep simulator-valid, ordinary constructible, and record-eligible as distinct predicates.
- [ ] Prove repeat verification is deterministic for identical cached artifacts and pinned verifier inputs.

### WP-10: solution parsing and normalization

- [ ] Implement a deterministic `.solution` parser behind the normalization seam.
- [ ] Implement `SolutionNormalizer` over parsed solution artifacts.
- [ ] Ensure every normalized solution identifies its exact source `SolutionArtifact` and normalizer version.
- [ ] Keep normalization failures independent from verification success or failure.
- [ ] Generate normalized records from canonical artifacts instead of maintaining production normalized JSONL by hand.

### WP-11: connect canonical entities to the release factory

- [ ] Materialize canonical puzzle, solution, observation, verification-derived, and normalized rows into the existing four release inputs.
- [ ] Derive release rows rather than introducing a parallel canonical row store.
- [ ] Preserve verification-derived metrics without trusting source-declared scores.
- [ ] Preserve payload-rights enforcement through materialization and publication.
- [ ] Prove repeated offline materialization produces identical canonical row content and release manifest hashes.
- [ ] Keep `fixtures/tiny-corpus/` as a test fixture only, not production authority.

### WP-12: reach the v1 release boundary

- [ ] Run the full frozen `base-game-2026-06-16` pipeline from pinned cached source facts.
- [ ] Ensure every required puzzle has at least one verifier-successful solution or fail the complete build.
- [ ] Ensure every published solution is traceable to immutable source evidence.
- [ ] Derive missing coverage and source/verifier discrepancies mechanically rather than repairing them by hand.
- [ ] Record collection hash, source revisions, artifact hashes, verifier identity, validation profile, normalizer version, coverage, and output hashes in the release manifest.
- [ ] Rebuild offline from the same cache and confirm the canonical release manifest is reproduced.
- [ ] Pass [`hugging-face-export.md`](hugging-face-export.md) with the complete real corpus.
- [ ] Publish the first complete base-game release as a downstream projection.

## Later

### Research-grade derived views and benchmark harness

- [ ] Generate all-verified, vanilla/ordinary-constructible, and record-eligible solution views.
- [ ] Generate Pareto frontiers and best-known cost/cycles/area/instructions views using explicit versioned predicates.
- [ ] Generate human-observed versus machine-generated solution views.
- [ ] Implement a deterministic model-oriented puzzle serialization over normalized puzzle records.
- [ ] Implement the v0.1 Solve benchmark harness defined in [`benchmark-protocol.md`](benchmark-protocol.md).
- [ ] Support one-shot and one bounded interactive attempt profile with versioned feedback.
- [ ] Generate per-puzzle result records and deterministic aggregate benchmark reports.
- [ ] Derive best-known reference metrics/frontiers from verifier-successful canonical solutions.
- [ ] Design leakage-aware benchmark train/validation/test or held-out collection methodology before introducing splits or making generalization claims.
- [ ] Keep every research and benchmark view derivable from canonical facts by versioned deterministic software.

### Expand beyond the frozen base game

- [ ] Define a De Re Metallica collection if source and validation semantics are ready.
- [ ] Define additional official/special puzzle collections as immutable manifests rather than extending the frozen base-game manifest.
- [ ] Define Workshop/custom puzzle collection policy and provenance rules.
- [ ] Define tournament/community collection manifests where source identity is sufficiently stable.
- [ ] Add additional historical solution archives through the existing adapter/acquisition path.
- [ ] Add clearly identified machine-generated baselines, such as OpusSolver output, as source facts with explicit provenance.
- [ ] Extend shared infrastructure only when a new source class genuinely requires a new primitive.

## Cross-cutting rules

- [ ] Reuse an existing primitive before adding storage, reconciliation, projection, or orchestration machinery.
- [ ] Put repeatable bookkeeping, counting, validation, reconciliation, and materialization in deterministic software.
- [ ] Keep repository facts authoritative and publication/benchmark surfaces derived.
- [ ] Preserve source evidence even when it conflicts with verifier-derived facts.
- [ ] Treat rights status per artifact/source class; do not infer redistribution permission from technical availability or the repository's MIT license.
- [ ] Fail closed on unknown identity, unknown required puzzle fields, corruption, verification failure, or rights uncertainty.
- [ ] Keep v1 deduplication at exact-byte identity only.
- [ ] Add focused regression tests for each invariant before considering a slice complete.

## Done when

V1 is done when the release acceptance criteria in [`dataset-spec.md`](dataset-spec.md) are satisfied for `base-game-2026-06-16`: the complete verifier-backed corpus can be rebuilt offline from pinned cached facts, all required solutions have immutable provenance and recomputed metrics, generated views require no manual corpus maintenance, and the existing release pipeline can publish the resulting downstream projection.