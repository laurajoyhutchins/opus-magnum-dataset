# TODO

This checklist translates the strategic [`roadmap.md`](roadmap.md) into the next concrete implementation slices.

It is not the authority for work state. GitHub pull requests and issues remain the repository execution record, while the Hatchable Portfolio Control Plane owns live work claims and settlement. Generated coverage, verification counts, manifests, and other derivable facts must come from repository software rather than hand-maintained entries here.

Use this file to answer two questions: **what can be worked on concurrently without overlapping ownership, and what should we build next in dependency order?**

## Work graph

This is the static concurrency map plus a coarse execution snapshot. It defines dependencies and ownership boundaries; the Hatchable Portfolio Control Plane remains authoritative for live claims and settlement (`work.claim` / `work.settle`). Landed packets are marked here to prevent agents from reclaiming completed architectural work, and in-progress markers are only navigation aids.

```text
[LANDED] WP-01 Verification contract (#13)
        │
        └──────────────→ [LANDED] WP-02 Normalized-solution contract (#14)

[IN PROGRESS] WP-03 Artifact materializer core
        │
        └────→ WP-04 SolutionArtifact + Observation materialization ────┐
                                                                        │
[IN PROGRESS] WP-05 omsim puzzle source ────────┐                       │
[LANDED] WP-06 molecule-db semantic source (#18) ├→ WP-08 PuzzleArtifact│
[LANDED] WP-07 official/local puzzle-byte path (#16) ┘ coverage/materialization
                                                    │                   │
[LANDED] WP-01 ────────────────────────────────────┼──────┐            │
                                                    ↓      │            │
                                              WP-09 Verification ←──────┘
                                                    │
[LANDED] WP-02 ──────────────────────┐              │
WP-04 ───────────────────────────────┴→ WP-10 Solution parser + normalizer
                                                    │
WP-04 ──────────────────────────────────────────────┐
WP-08 ──────────────────────────────────────────────┤
WP-09 ──────────────────────────────────────────────┼→ WP-11 Release materialization
WP-10 ──────────────────────────────────────────────┘
                                                    │
                                                    ↓
                                            WP-12 Complete v1 release

Independent hardening lane
  #20 staging source/destination overlap
      ↓  shared publish.py surface; serialize to avoid branch collision
  #21 manifest path confinement
      ↓  shared release.py surface; serialize to avoid branch collision
  #23 manifest format-version gate

  #22 schema-resolution/package-layout fix  (may run in parallel)

All four hardening issues should settle before WP-11 begins modifying the
release boundary in earnest.
```

The active architectural lanes are WP-03 and WP-05. WP-01, WP-02, WP-06, and WP-07 are settled foundations on `main`. Downstream packets should not start by reimplementing missing upstream behavior; they should consume the declared interfaces when those dependencies settle.

The hardening issues are independent of the canonical-materialization dependency spine, but not all are safe to implement simultaneously. Issues #20 and #21 both modify staging behavior, and #21 and #23 both modify release validation. Their sequencing above is for collision avoidance, not because one issue is semantically required by the next. Issue #22 has a separate schema/package surface and can proceed beside them.

### Landed foundations

These capabilities already exist and should be consumed rather than recreated:

- [x] Frozen `base-game-2026-06-16` collection and collection validation.
- [x] Four-config deterministic release shell with Parquet, manifest, dataset card, staging, and publication guards.
- [x] Explicit `complete` / `subset` coverage policy with mechanically derived per-puzzle release coverage.
- [x] Rights-aware payload policy, including metadata-only publication.
- [x] Content-addressed acquisition cache with immutable receipts and source-mutation protection.
- [x] Explicit source fetch CLI.
- [x] Pinned `om-archive` acquisition.
- [x] Pinned `om-leaderboard` acquisition.
- [x] Source-adapter contract and fail-closed stubs for unimplemented sources.
- [x] Normalized-puzzle schema and deterministic serialization seam.
- [x] Exact `PuzzleArtifact` lineage requirement for normalized puzzle rows.
- [x] Canonical Verification contract from PR #13.
- [x] Strict normalized-solution contract and `SolutionNormalizer` seam from PR #14.
- [x] Pinned molecule-db semantic acquisition and topology reconciliation from PR #18.
- [x] Explicit local official `.puzzle` acquisition with immutable manifest provenance, filesystem-safe snapshot identity, and `local_fetch_only` rights from PR #16.

### Claimable work packets

Each open packet owns one capability. A worker may change adjacent code only when required to consume an existing interface; extending or redesigning another packet's interface belongs to that packet. Settled packets remain listed because downstream dependencies refer to them, but they must not be claimed again.

| Packet | State | Depends on | Owns | Consumes → produces | Do not touch | Settle when |
| --- | --- | --- | --- | --- | --- | --- |
| **WP-01 Verification contract** | **Settled** | current `main` at implementation time | Canonical `Verification` schema, identity, protocol, contract tests | artifact/verifier identities → simulator-independent verification contract | acquisition, cache, normalization, release materialization | PR #13 merged with contract tests green |
| **WP-02 Normalized-solution contract** | **Settled** | WP-01 | Strict normalized-solution schema, deterministic identity, `SolutionNormalizer` seam | parsed/identified solution inputs → parser-independent normalization contract | `.solution` parser, verifier implementation, acquisition, release wiring | PR #14 merged with contract tests green |
| **WP-03 Artifact materializer core** | **In progress** | landed content-addressed cache | Shared canonical artifact/provenance materialization primitive and content-derived identity | cached immutable objects + receipts → canonical artifact/provenance records | source-specific parsers, second object store, verification, normalization, release projection | exact-byte identity, provenance merge, corruption/conflict, ordering, and local-root invariants are tested |
| **WP-04 SolutionArtifact + Observation materialization** | Blocked | WP-03 | Deterministic conversion of acquired solution/metadata facts into canonical solution artifacts and observations | `om-archive` / `om-leaderboard` cached facts → `SolutionArtifact` + `Observation` records | source acquisition mechanisms, puzzle-definition adapters, verification, normalization | overlapping sources dedupe by bytes while observations and source claims remain preserved |
| **WP-05 omsim puzzle source** | **In progress** | landed acquisition/cache primitives | Pinned `omsim` puzzle-definition acquisition/adapter behavior | pinned `omsim` source → cached puzzle-definition facts | canonical artifact schemas, solution parsing, verifier semantics, release rows | source mapping is deterministic, idempotent, rights-aware, and covered by fixtures/tests |
| **WP-06 molecule-db semantic source** | **Settled** | landed acquisition/cache primitives | Pinned molecule-db semantic acquisition/adapter behavior | pinned molecule-db source → cached semantic puzzle evidence | exact official-byte claims, canonical artifact schemas, verification, release rows | PR #18 merged with semantic acquisition/reconciliation tests green |
| **WP-07 Official/local puzzle-byte path** | **Settled** | landed acquisition/cache primitives | Explicit local acquisition path for exact official puzzle bytes where needed | local permitted official bytes → cached immutable puzzle-byte facts | invented game fields, semantic substitution, alternate object storage, verification | PR #16 merged with exact-byte, provenance, rights, portability, and fail-closed regression coverage green |
| **WP-08 PuzzleArtifact coverage/materialization** | Blocked | WP-03, WP-05, WP-06, WP-07 | Canonical puzzle artifact materialization and deterministic verifier-usable coverage | cached puzzle facts/evidence → `PuzzleArtifact` records + derived coverage | new fetch/cache mechanisms, verifier execution, release projections | every required puzzle can resolve a verifier-usable artifact or the coverage computation fails explicitly |
| **WP-09 Verification implementation** | Blocked | WP-01, WP-04, WP-08 | Pinned `omsim`/`libverify` implementation behind `Verifier`; canonical verification records | exact puzzle + solution artifacts → deterministic `Verification` records | source acquisition, canonical artifact storage, normalized schema, release selection logic | parse/simulation success and failure are retained, metrics are recomputed, repeat runs are deterministic |
| **WP-10 Solution parser + normalizer** | Blocked | WP-02, WP-04 | Deterministic `.solution` parser and `SolutionNormalizer` implementation | exact `SolutionArtifact` → normalized solution record | verifier authority, acquisition/cache, release materialization, model-specific serializers | normalized records carry exact artifact lineage/version; normalization failures do not alter verification facts |
| **WP-11 Release materialization** | Blocked | WP-04, WP-08, WP-09, WP-10 | Deterministic projection from canonical entities into the existing four release inputs | canonical artifacts/observations/verifications/normalized records → release rows | new canonical stores, alternate release formats, source adapters, manual coverage state | repeated offline materialization yields identical canonical rows/manifest hashes and existing release validation passes |
| **WP-12 Complete v1 release** | Blocked | WP-11 | Full frozen-collection build, gap diagnosis through upstream fixes, publication readiness | pinned cached facts + deterministic pipeline → complete `base-game-2026-06-16` release | hand repairs, exceptions that weaken complete coverage, parallel publication authority | all 166 puzzles have verifier-successful coverage, offline rebuild reproduces the canonical manifest, HF contract passes |

### Independent hardening issues

GitHub issues are the authority for their detailed acceptance criteria. This section exists only to place them safely relative to the work packets.

| Issue | Execution | Surface | Relationship to work graph |
| --- | --- | --- | --- |
| [#20 Reject overlapping source and destination paths when staging releases](https://github.com/laurajoyhutchins/opus-magnum-dataset/issues/20) | Open; first in release-hardening sequence | `publish.py`, stage CLI | Independent of active WP-03/05; settle before #21 and WP-11 |
| [#21 Constrain release manifest paths to the release root](https://github.com/laurajoyhutchins/opus-magnum-dataset/issues/21) | Open; after #20 | `release.py`, `publish.py` | Independent semantics, serialized after #20 to avoid staging-surface collision; settle before #23/WP-11 |
| [#22 Unify schema resolution and remove repository-layout dependency](https://github.com/laurajoyhutchins/opus-magnum-dataset/issues/22) | Open; parallel | `collections.py`, `release_inputs.py`, config, packaging | Separate surface; may proceed beside architectural packets and release hardening |
| [#23 Reject unsupported release manifest format versions](https://github.com/laurajoyhutchins/opus-magnum-dataset/issues/23) | Open; after #21 | `release.py` | Independent semantics, serialized after #21 to avoid release-validation collision; settle before WP-11 |

### Agent execution rules

1. Claim exactly one open packet or issue before implementation. Use the control-plane claim as the live concurrency lock; do not add assignee bookkeeping to this file.
2. Never claim a packet marked **Settled**. Consume its landed interface from `main`.
3. Do not start a second item whose declared implementation surface overlaps an active item unless the graph explicitly allows it. The hardening sequence above exists specifically to avoid shared-file trampling.
4. Branch from the packet's declared settled dependency base. A stacked PR is appropriate only when the graph contains that dependency edge or a collision-avoidance sequence explicitly calls for it.
5. Own the capability, not neighboring machinery. If required work changes another packet's public contract, stop and split or restack rather than silently widening scope.
6. Reuse established primitives. In particular, no packet may create a second content store, snapshot authority, canonical row authority, verification authority, or release path.
7. Make dependencies explicit in the PR body and keep non-goals explicit enough that another agent can safely work beside it.
8. Settle only with fresh deterministic evidence for the packet's acceptance criteria. Downstream workers consume settled contracts rather than copying unfinished implementations.
9. If two items unexpectedly need the same implementation surface, fix the graph or factor a smaller shared primitive before continuing. Do not resolve the collision by allowing both workers to mutate it independently.

## Now

### Active architectural work

- [ ] WP-03: establish the one canonical artifact-materialization path on top of the existing content-addressed acquisition cache. **In progress.**
- [ ] WP-05: implement the `omsim` puzzle-definition source against the shared acquisition/cache boundary. **In progress.**
- [x] WP-06: implement the molecule-db semantic source. Landed in PR #18.
- [x] WP-07: implement the official/local exact puzzle-byte acquisition path. Landed in PR #16.

### Release and package hardening

- [ ] Issue #20: reject overlapping staging source/destination trees.
- [ ] Issue #21: constrain manifest-controlled artifact paths to the release root.
- [ ] Issue #22: unify schema resolution and remove source-checkout/package-layout dependence.
- [ ] Issue #23: reject unsupported release-manifest format versions.

### Finished contract stack

- [x] Land the canonical Verification contract in [PR #13](https://github.com/laurajoyhutchins/opus-magnum-dataset/pull/13).
  - [x] Keep `Verification` independent of any particular simulator implementation.
  - [x] Keep identity deterministic from puzzle artifact, solution artifact, verifier identity, and validation profile.
  - [x] Preserve the existing release-row projection boundary rather than embedding materialization logic in the contract layer.
- [x] Finish and land the normalized-solution contract in [PR #14](https://github.com/laurajoyhutchins/opus-magnum-dataset/pull/14).
  - [x] Make parts, tracks, programs, instructions, and deterministic summaries strict rather than permissive blobs.
  - [x] Make `normalized_solution_id` deterministic.
  - [x] Add the parser-independent `SolutionNormalizer` seam.
  - [x] Keep serialization as a projection over normalized records.

### Establish the one artifact-materialization path

- [ ] Define the canonical materialization slice on top of the existing content-addressed acquisition cache.
- [x] Reuse the landed cache/object primitive for canonical artifact access; do not create a second object store or extracted-snapshot authority.
- [ ] Port only the non-duplicative artifact/provenance contracts worth preserving from the closed artifact-ingestion work:
  - [ ] observed artifact candidate shape;
  - [ ] canonical artifact record shape;
  - [ ] provenance record shape;
  - [ ] deterministic content-derived artifact identity;
  - [ ] exact-byte deduplication with multi-source provenance;
  - [ ] conservative rights aggregation;
  - [ ] fail-closed identity/format conflict handling.
- [ ] Add regression coverage for source mutation, corrupt cached objects, deterministic ordering, and local-root independence.

## Next

### Materialize canonical source facts

- [ ] Materialize cached puzzle bytes as canonical `PuzzleArtifact` records.
- [ ] Materialize cached solution bytes as canonical `SolutionArtifact` records.
- [ ] Materialize source sightings and source metadata as canonical `Observation` records.
- [ ] Deduplicate only exact byte-identical artifacts by SHA-256.
- [ ] Preserve multiple observations when multiple sources expose the same artifact.
- [ ] Preserve source-declared metrics as observations rather than treating them as verified values.
- [ ] Fail closed on ambiguous puzzle mapping, incompatible formats, corrupt objects, or source mutation.

### Complete verifier-ready puzzle-definition coverage

- [ ] Implement the `omsim` puzzle-definition adapter against the shared acquisition/cache boundary.
- [x] Implement the molecule-db semantic adapter against the shared acquisition/cache boundary.
- [x] Define the official-game/local puzzle-byte acquisition path for exact official `.puzzle` fidelity where required.
- [x] Keep exact puzzle bytes distinct from semantic evidence such as molecule topology.
- [ ] Generate deterministic puzzle-artifact coverage from canonical facts.
- [ ] Make a complete base-game build fail unless every required puzzle resolves to at least one verifier-usable `PuzzleArtifact`.

### Integrate deterministic verification

- [ ] Pin the verifier implementation/revision and validation-profile identity used for v1.
- [ ] Implement the `Verifier` protocol using `omsim`/`libverify`.
- [ ] Parse exact puzzle and solution artifacts through the verification path.
- [ ] Emit canonical `Verification` records for successful and failed attempts.
- [ ] Recompute at least cost, cycles, area, and instructions for successful verifications.
- [ ] Preserve structured parse and simulation failures as canonical data.
- [ ] Keep simulator-valid, ordinary constructible, and record-eligible as distinct predicates.
- [ ] Prove repeat verification is deterministic for identical cached artifacts and pinned verifier inputs.

### Normalize solutions and puzzles from canonical artifacts

- [ ] Implement a deterministic `.solution` parser behind the normalization seam.
- [ ] Implement `SolutionNormalizer` over parsed solution artifacts.
- [ ] Ensure every normalized solution identifies its exact source `SolutionArtifact` and normalizer version.
- [x] Keep every normalized puzzle linked to its exact source `PuzzleArtifact`.
- [ ] Keep normalization failures independent from verification success or failure.
- [ ] Generate normalized records from canonical artifacts instead of maintaining production normalized JSONL by hand.

### Connect canonical entities to the release factory

- [ ] Add deterministic production materialization from canonical entities into the existing `puzzles`, `solutions`, `observations`, and `normalized` release inputs.
- [ ] Derive release rows rather than introducing a parallel canonical row store.
- [ ] Include verification-derived metrics without trusting source-declared scores.
- [x] Preserve payload-rights enforcement through materialization and publication.
- [ ] Prove repeated offline materialization produces identical canonical row content and release manifest hashes.
- [x] Keep `fixtures/tiny-corpus/` as a test fixture only, not production authority.

### Reach the v1 release boundary

- [ ] Run the full frozen `base-game-2026-06-16` pipeline from pinned cached source facts.
- [x] Require all 166 collection puzzles to be present in a `complete` release.
- [x] Require at least one verifier-successful solution per required puzzle; otherwise fail the complete build.
- [ ] Ensure every published solution is traceable to immutable source evidence.
- [ ] Derive missing coverage and source/verifier discrepancies mechanically rather than repairing them by hand.
- [ ] Record collection hash, source revisions, artifact hashes, verifier identity, validation profile, normalizer version, coverage, and output hashes in the release manifest.
- [ ] Rebuild offline from the same cache and confirm the canonical release manifest is reproduced.
- [x] Validate rights-aware metadata-only publication for restricted raw payloads.
- [ ] Pass the Hugging Face export contract in `hugging-face-export.md` with the complete real corpus.
- [ ] Publish the first complete base-game release as a downstream projection.

## Later

### Research-grade derived views

- [ ] Generate an all-verified-solutions view.
- [ ] Generate ordinary/vanilla-constructible and record-eligible views from explicit versioned predicates.
- [ ] Generate Pareto frontiers for declared metric tuples.
- [ ] Generate best-cost, best-cycles, best-area, and best-instructions views.
- [ ] Generate human-observed versus machine-generated solution views.
- [ ] Design and generate one-per-puzzle benchmark selections.
- [ ] Add model-oriented text/token serializers over normalized records when experiments justify them.
- [ ] Design benchmark train/validation/test methodology before adding dataset splits.
- [ ] Keep every research view derivable from canonical facts by versioned deterministic software.

### Expand the corpus beyond the frozen base game

- [ ] Define a De Re Metallica collection if source and validation semantics are ready.
- [ ] Define additional official/special puzzle collections as immutable manifests rather than extending the frozen base-game manifest.
- [ ] Define Workshop/custom puzzle collection policy and provenance rules.
- [ ] Define tournament/community collection manifests where source identity is sufficiently stable.
- [ ] Add additional historical solution archives through the existing adapter/acquisition path.
- [ ] Add clearly identified machine-generated baselines, such as OpusSolver output, as source facts with explicit provenance.
- [ ] Extend shared infrastructure only when a new source class genuinely requires a new primitive.

## Cross-cutting rules for every slice

- [ ] Reuse an existing primitive before adding orchestration, storage, reconciliation, or projection machinery.
- [ ] Put repeatable bookkeeping, counting, validation, reconciliation, and materialization in deterministic software.
- [ ] Keep GitHub repository facts authoritative and publication surfaces derived.
- [ ] Preserve source evidence even when it conflicts with verifier-derived facts.
- [ ] Treat rights status per artifact/source class; do not infer redistribution permission from technical availability.
- [ ] Fail closed on unknown identity, unknown required puzzle fields, corruption, verification failure, or rights uncertainty.
- [ ] Keep v1 deduplication at exact-byte identity only.
- [ ] Add focused regression tests for each invariant before considering a slice complete.

## Done when

V1 is done when the release acceptance criteria in [`dataset-spec.md`](dataset-spec.md) are satisfied for `base-game-2026-06-16`: the complete verifier-backed corpus can be rebuilt offline from pinned cached facts, all required solutions have immutable provenance and recomputed metrics, generated views require no manual corpus maintenance, and the existing release pipeline can publish the resulting downstream projection.
