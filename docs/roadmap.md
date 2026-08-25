# Roadmap

This roadmap defines the strategic dependency order from source facts to a reproducible Opus Magnum corpus and research surface. It is intentionally not a task tracker.

Live execution state belongs in GitHub issues and pull requests. [`TODO.md`](TODO.md) records only stable dependency/concurrency topology. Coverage counts, current PRs, active/blocked labels, generated manifests, verification results, and other fast-moving or derivable state do not belong here.

## Architectural path

```text
immutable collection definitions
        ↓
pinned source acquisition
        ↓
content-addressed source cache + provenance receipts
        ↓
canonical semantic facts + exact PuzzleArtifact / SolutionArtifact / Observation records
        ↓
exact-artifact verification
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

## Milestone 1: Verification and normalization contracts

**Goal:** Define canonical verification and normalized-solution boundaries independently from parser- or simulator-specific implementations.

The contract layer fixes deterministic identities, strict schemas, implementation seams, and the distinction between source observations, verifier-derived facts, normalized structures, and serializers. Result values do not define evaluation identity, and normalized representations do not replace exact artifacts or provenance.

## Milestone 2: Canonical artifact materialization

**Goal:** Convert acquired source facts into canonical artifact/provenance records without introducing another byte store.

Exact puzzle and solution bytes use one content-addressed storage path. Artifact identity is content-derived, exact-byte SHA-256 is the v1 deduplication boundary, multiple sources preserve multiple observations, and conflicting or corrupt facts fail closed.

## Milestone 3: Puzzle-definition acquisition

**Goal:** Acquire verifier-usable exact puzzle artifacts while keeping exact bytes distinct from semantic problem evidence.

Pinned and local source adapters translate upstream facts into the common acquisition/cache boundary. Semantic evidence may establish puzzle structure without pretending to be an exact official binary artifact. Exact artifacts retain explicit format, hash, rights, and provenance. Collection membership remains repository authority rather than being redefined by an adapter.

## Milestone 4: Deterministic verification

**Goal:** Make deterministic verifier results, not source claims, authoritative for executable validity and computed metrics.

The verifier consumes exact puzzle/solution artifacts under a pinned implementation and validation profile, recomputes canonical metrics, preserves structured parse/simulation failures, and keeps source-declared observations independently. Simulator validity, ordinary constructibility, and record eligibility remain separate predicates.

## Milestone 5: Normalization and release materialization

**Goal:** Derive normalized solution structures and canonical release inputs from canonical facts without a second corpus authority.

Parsing and normalization retain exact artifact lineage and version identity. Release materialization projects canonical puzzle, solution, observation, verification-derived, and normalized facts into the existing release configs while preserving rights policy and deterministic ordering. Fixture data remains test data, not production authority.

## Milestone 6: Complete frozen base-game release

**Goal:** Produce a stable complete corpus for `base-game-2026-06-16` through one deterministic offline release boundary.

Exit criteria:

- the frozen collection materializes from permitted, pinned cached inputs;
- every required puzzle is present and has verifier-successful coverage, otherwise the complete build fails;
- every published artifact and solution is traceable to immutable source evidence;
- headline metrics are recomputed by the pinned verifier rather than trusted from source metadata;
- missing coverage and source/verifier discrepancies are derived and reported, never manually repaired;
- the release manifest records collection, source, artifact, verifier, normalizer, coverage, and output identities needed for reproduction;
- rebuilding offline from the same authoritative inputs reproduces the canonical release manifest;
- rights policy is enforced at publication time;
- the Hugging Face projection satisfies [`hugging-face-export.md`](hugging-face-export.md).

This is the v1 release boundary. Publication is downstream of a validated release and does not become corpus authority.

## Milestone 7: Research-grade views and benchmarks

**Goal:** Turn canonical corpus facts into useful research surfaces without introducing hand-maintained datasets or benchmark ledgers.

The benchmark architecture in [`benchmark-protocol.md`](benchmark-protocol.md) separates protocol identity from collection identity, starts with verifier-backed Solve evaluation, preserves Opus Magnum's multi-objective metrics, and distinguishes public-corpus evaluation from held-out generalization claims.

The first research wave is split into four capability boundaries:

- **WP-13: deterministic puzzle serializer.** A versioned model-oriented serialization over canonical puzzle semantics, with golden and determinism tests. It is a projection, not a second dataset. The durable serialization contract lives in [`puzzle-serialization.md`](puzzle-serialization.md).
- **WP-14: verifier-derived reference views.** Deterministic verified, constructibility/eligibility, best-known-metric, and Pareto-frontier views from canonical facts and explicit predicates.
- **WP-15: benchmark result model and deterministic aggregation.** Stable benchmark/run/attempt/per-puzzle identities, failure taxonomy, and reproducible aggregate reporting independent from any particular model runner.
- **WP-16: v0.1 Solve harness.** Consume the serializer, result model, and pinned verifier to execute exact-artifact Solve evaluation and emit deterministic reports. Reference views supply comparison metrics where the protocol requests them.

WP-13, WP-14, and WP-15 are deliberately separable derived surfaces. WP-16 is the integration boundary downstream of the serializer and result model. Bounded interactive evaluation, Optimize, Frontier, Repair, and Constrained tracks should extend the same protocol only after the exact-output Solve path is stable.

Any train/validation/test projection requires an explicit leakage-aware methodology. Every research view must remain versioned, testable, and derivable from canonical facts.

## Milestone 8: Expand beyond the frozen base game

**Goal:** Reuse the same canonical pipeline for additional Opus Magnum problem and solution classes.

Potential families include De Re Metallica, other official/special puzzle sets, Workshop/custom puzzles, tournament/community collections, additional historical archives, and clearly identified machine-generated baselines.

Expansion rules:

- express new scope through new immutable collection definitions rather than mutating the frozen base-game collection;
- translate new source facts through existing acquisition and canonical boundaries rather than redefining identities or schemas per source;
- keep rights, provenance, validation semantics, and coverage explicit per source/artifact class;
- extend shared deterministic infrastructure only when a genuinely new primitive is required.

## Ordering and parallelism

The core dependency spine is:

```text
contracts
  → artifact materialization
  → puzzle-definition evidence/artifacts
  → verification
  → normalization
  → release materialization
  → complete release
  → research integration
```

The research wave branches from canonical primitives:

```text
                              ┌─ WP-13 puzzle serializer ──┐
canonical corpus primitives ─┼─ WP-15 result/report model ├─→ WP-16 Solve harness
                              └─ WP-14 reference views ────┘
                                         │
                                         └─→ reference metrics/frontiers
```

Whether a packet is open, merged, blocked, under review, or superseded is intentionally absent from this roadmap. Inspect GitHub for live execution state and [`TODO.md`](TODO.md) for the stable ownership/dependency topology.

## Decision rules

When choosing implementation work, preserve these invariants:

1. **One authoritative path.** Reuse existing acquisition, storage, canonicalization, verification, normalization, and release primitives before adding another mechanism.
2. **Software derives state.** Repeated bookkeeping, reconciliation, counting, materialization, and known recovery behavior belong in deterministic software.
3. **Reasoning is for judgment work.** Use reasoning for research, design, synthesis, and novel implementation rather than maintenance of generated projections.
4. **Fail closed.** Unknown required fields, ambiguous identities, corrupt cached objects, verifier failures, unsafe filesystem states, and rights uncertainty remain explicit.
5. **Preserve evidence.** Source claims and deterministic verification may disagree; retain both with distinct provenance.
6. **Keep rights orthogonal to metadata utility.** Restricted raw bytes do not prevent permitted provenance, hashes, verified metrics, or derived facts from being published.
7. **Defer semantic deduplication.** V1 deduplicates exact bytes only. Any semantic-equivalence layer requires a separately versioned derived algorithm.

## V1 definition of done

V1 is a complete verifier-backed, provenance-preserving corpus for `base-game-2026-06-16` that can be rebuilt offline from pinned cached facts and exported through the existing release pipeline without manual corpus maintenance. The detailed acceptance contract lives in [`dataset-spec.md`](dataset-spec.md).
