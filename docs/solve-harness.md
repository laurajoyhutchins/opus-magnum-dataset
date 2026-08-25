# Exact-output Solve harness v0.1

The public Solve harness is the deterministic integration boundary for the v0.1 exact-output benchmark. It composes existing repository contracts; it does not create another source of corpus membership, candidate semantics, verifier behavior, or benchmark truth.

The public entry point is `opus_corpus.solve_benchmark.run_solve_benchmark`.

## Inputs

`run_solve_benchmark` consumes authoritative or derived facts that already have owners:

- a validated `CollectionDefinition` for collection identity and canonical membership;
- a `BenchmarkEligibilityProjection` produced by the benchmark-eligibility contract;
- canonical semantic `PuzzleDefinition` records;
- exact selected puzzle-artifact bytes keyed by artifact ID;
- a provider-neutral `SolveRunner` exposing a stable `SolverIdentity` and `generate(...)` seam;
- a canonical `Verifier` exposing its exact `VerifierIdentity` and `verify(...)` operation;
- a positive bounded `attempt_budget`, defaulting to one attempt.

The harness does not rediscover benchmark membership. Only `eligibility.executable_entries` execute. The full eligibility projection remains attached to the returned result so deterministic exclusion reasons remain available for non-executable puzzles.

## Execution path

For each executable puzzle, sorted by `puzzle_id`, the harness performs one bounded sequential transition:

1. Validate that collection, eligibility, semantic-definition, selected-artifact, and verifier identities agree.
2. Verify the exact selected puzzle-artifact byte length and SHA-256 before model execution.
3. Serialize the canonical semantic puzzle definition with `ModelPuzzleTextSerializer`.
4. Call the supplied `SolveRunner` with the puzzle ID, serialized puzzle text, and attempt index.
5. Compile raw model output with the repository-owned benchmark candidate-output compiler.
6. Parse the compiled `.solution` bytes and check puzzle binding before invoking the verifier.
7. Verify the exact puzzle bytes and exact compiled candidate bytes through the supplied pinned verifier.
8. Derive a WP-15 attempt record, then a per-puzzle result.
9. Stop attempts for that puzzle after the first verifier success or after the attempt budget is exhausted.
10. Aggregate all executable puzzle results through the canonical WP-15 report builder.

The harness never synthesizes missing puzzle artifacts and never weakens verification because bytes are unavailable.

## Outcome mapping

The harness preserves the WP-15 top-level outcome taxonomy:

| Boundary | Outcome | Verifier calls |
| --- | --- | ---: |
| Candidate envelope cannot compile | `output_compile_failed` | 0 |
| Compiled candidate cannot be parsed as a solution | `solution_parse_failed` | 0 |
| Parsed solution names a different puzzle | `puzzle_solution_mismatch` | 0 |
| Verifier parses the candidate but simulation does not pass | `simulation_failed` | 1 |
| Verifier passes and returns complete metrics | `success` | 1 |

A verifier-originated parse failure also maps to `solution_parse_failed`, but carries verifier lineage and one verifier call. Pre-verifier parse failures carry the exact compiled candidate hash without fake verifier lineage.

## Identity and reproducibility

The benchmark identity is derived from executable semantic dependencies, including:

- Solve protocol version;
- collection ID and canonical manifest hash;
- serializer name and version;
- candidate-output compiler name and version;
- executable-inventory SHA-256;
- verifier implementation, revision, binary SHA-256, and validation profile;
- attempt profile and attempt budget;
- scoring/reporting version.

The run identity additionally commits to the solver system ID and revision, harness implementation/revision, and generation-configuration hash when supplied.

The harness validates verifier result identity against the exact verification input before accepting the result. A verifier cannot silently report a different artifact, solution, revision, binary, or validation profile.

## Determinism and authority

Execution order is derived by sorting executable entries by `puzzle_id`; caller iteration order for definitions or other authoritative inputs cannot change canonical report bytes. WP-15 canonical reporting remains responsible for normalized result ordering and hashes.

`SolveBenchmarkResult` contains the eligibility projection, canonical per-puzzle result records, and the aggregate report. These are generated projections. They are not a persistent benchmark database, leaderboard authority, or replacement corpus.

Model providers remain outside repository authority. A provider adapter may implement `SolveRunner`, but the repository contract begins at the runner seam and records the runner identity needed to reproduce the run.

## Scope boundary

This v0.1 path is Solve-only. It does not implement Optimize, Frontier, Repair, Constrained, interactive tracks, split methodology, a benchmark store, or acquisition of missing official puzzle bytes. Expanded hermetic end-to-end coverage belongs downstream; the public integration path itself stays thin and composes the deterministic operators already owned elsewhere in the repository.
