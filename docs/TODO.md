# TODO

This checklist translates the strategic [`roadmap.md`](roadmap.md) into the next concrete implementation slices.

It is not the authority for work state. GitHub pull requests and issues remain the live execution surface, and generated coverage, verification counts, manifests, and other derivable facts must come from repository software rather than hand-maintained entries here.

Use this file to answer one question: **what should we build next, in dependency order?**

## Now

### Finish the contract stack

- [ ] Land the canonical Verification contract in [PR #13](https://github.com/laurajoyhutchins/opus-magnum-dataset/pull/13).
  - [ ] Keep `Verification` independent of any particular simulator implementation.
  - [ ] Keep identity deterministic from puzzle artifact, solution artifact, verifier identity, and validation profile.
  - [ ] Preserve the existing release-row projection boundary rather than embedding materialization logic in the contract layer.
- [ ] Finish and land the normalized-solution contract in [PR #14](https://github.com/laurajoyhutchins/opus-magnum-dataset/pull/14).
  - [ ] Make parts, tracks, programs, instructions, and deterministic summaries strict rather than permissive blobs.
  - [ ] Make `normalized_solution_id` deterministic.
  - [ ] Add the parser-independent `SolutionNormalizer` seam.
  - [ ] Keep serialization as a projection over normalized records.

### Establish the one artifact-materialization path

- [ ] Define the canonical materialization slice on top of the existing content-addressed acquisition cache.
- [ ] Reuse the landed cache/object primitive for canonical artifact access; do not create a second object store or extracted-snapshot authority.
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
- [ ] Implement the molecule-db semantic adapter against the shared acquisition/cache boundary.
- [ ] Define the official-game/local puzzle-byte acquisition path for exact official `.puzzle` fidelity where required.
- [ ] Keep exact puzzle bytes distinct from semantic evidence such as molecule topology.
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
- [ ] Keep every normalized puzzle linked to its exact source `PuzzleArtifact`.
- [ ] Keep normalization failures independent from verification success or failure.
- [ ] Generate normalized records from canonical artifacts instead of maintaining production normalized JSONL by hand.

### Connect canonical entities to the release factory

- [ ] Add deterministic production materialization from canonical entities into the existing `puzzles`, `solutions`, `observations`, and `normalized` release inputs.
- [ ] Derive release rows rather than introducing a parallel canonical row store.
- [ ] Include verification-derived metrics without trusting source-declared scores.
- [ ] Preserve payload-rights enforcement through materialization and publication.
- [ ] Prove repeated offline materialization produces identical canonical row content and release manifest hashes.
- [ ] Keep `fixtures/tiny-corpus/` as a test fixture only, not production authority.

### Reach the v1 release boundary

- [ ] Run the full frozen `base-game-2026-06-16` pipeline from pinned cached source facts.
- [ ] Require all 166 collection puzzles to be present in a `complete` release.
- [ ] Require at least one verifier-successful solution per required puzzle; otherwise fail the complete build.
- [ ] Ensure every published solution is traceable to immutable source evidence.
- [ ] Derive missing coverage and source/verifier discrepancies mechanically rather than repairing them by hand.
- [ ] Record collection hash, source revisions, artifact hashes, verifier identity, validation profile, normalizer version, coverage, and output hashes in the release manifest.
- [ ] Rebuild offline from the same cache and confirm the canonical release manifest is reproduced.
- [ ] Validate rights-aware metadata-only publication for restricted raw payloads.
- [ ] Pass the Hugging Face export contract in `hugging-face-export.md`.
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