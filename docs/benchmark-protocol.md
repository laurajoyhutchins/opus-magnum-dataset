# Benchmark Protocol

Status: **Draft v0.1**

This document defines how the Opus Magnum corpus can become a reproducible benchmark without turning benchmark results, executable subsets, or model-specific representations into new authorities.

The benchmark is a deterministic projection over the canonical corpus. A benchmark version fixes the protocol, collection, semantic puzzle serialization, candidate-output compiler, verifier, validation profile, attempt policy, and scoring/reporting rules used to evaluate a system.

## 1. Benchmark boundary

The core evaluation loop is:

```text
canonical PuzzleDefinition
        ↓
versioned puzzle serialization
        ↓
model / solver / agent
        ↓
raw candidate output
        ↓
deterministic candidate-output compiler
        ↓
exact solution artifact
        ↓
selected verifier-ready PuzzleArtifact + pinned verifier + validation profile
        ↓
validity + computed metrics + structured failure
        ↓
versioned benchmark report
```

The benchmark does not trust model-declared scores, filenames, source metadata, or natural-language claims of correctness. A submitted solution is successful only when it passes the pinned verifier under the benchmark's declared validation profile.

The canonical corpus remains the source of semantic puzzle identity, artifact provenance, reference solutions, verifier evidence, and derived reference frontiers. Benchmark inputs, executable inventories, and reports are derived state.

## 2. Protocol, collection, and executable inventory are separate

A benchmark protocol, benchmark collection, and executable benchmark inventory are distinct concepts.

The **protocol** defines:

- accepted puzzle input representation;
- accepted solution output representation;
- candidate-output compilation semantics;
- verifier and validation semantics;
- attempt budget and feedback policy;
- resource accounting;
- metrics and aggregation rules;
- result schema.

The **collection** defines the immutable semantic puzzle identities intended for evaluation.

The **executable inventory** is deterministically derived from the collection plus canonical semantic, artifact, and verifier-ready coverage for the chosen protocol. A puzzle may belong to the benchmark collection and have a complete `PuzzleDefinition` while being ineligible for an exact-artifact Solve execution because no verifier-usable `PuzzleArtifact` is available. That does not remove the puzzle from the collection or erase its semantic coverage.

Every exclusion from an executable inventory must have a stable machine-readable reason. Benchmark code must not maintain a hand-edited runnable-puzzle list.

This separation allows the same protocol to target `base-game-2026-06-16`, a held-out community collection, or a future official collection without redefining benchmark semantics, while still representing temporary or rights-constrained artifact availability honestly.

A benchmark identity should therefore commit to at least:

```text
protocol version
collection ID + manifest hash
executable inventory identity/hash
puzzle serializer version
candidate-output compiler version
verifier identity + hash/revision
validation profile version
attempt policy
scoring/reporting version
```

## 3. Initial benchmark track: Solve

The first benchmark track should be **Solve**.

Input:

- one canonical semantic puzzle from an immutable benchmark collection;
- a versioned deterministic serialization of its `PuzzleDefinition`;
- no reference solution.

Execution precondition:

- the protocol's derived executable inventory selects a verifier-usable exact `PuzzleArtifact` for that semantic puzzle.

Output:

- one raw candidate response that satisfies the benchmark-defined output envelope and deterministically compiles to exact `.solution` bytes.

Success:

- candidate output compiles;
- the exact solution artifact parses and is bound to the intended puzzle;
- the pinned verifier successfully simulates the candidate against the selected exact puzzle artifact;
- required deterministic metrics are produced.

The primary benchmark question is therefore simple: **Can the evaluated system produce a verifier-successful Opus Magnum machine for this semantic puzzle under the declared attempt policy and exact verification boundary?**

## 4. Additional tracks

Later protocol versions may define additional tracks without changing Solve semantics.

### Optimize

Input includes a puzzle plus a valid baseline solution or baseline metrics. The system attempts to produce a verifier-successful solution that improves one or more declared metrics.

### Frontier

The system may submit multiple valid solutions for one puzzle. Evaluation compares the generated nondominated set with a reference frontier using explicit multi-objective measures.

### Repair

Input includes a puzzle plus an invalid or suboptimal candidate. The system must return a verifier-successful repaired solution while preserving any explicitly declared constraints.

### Constrained solve

The puzzle is paired with additional benchmark constraints such as a part budget, metric ceiling, or allowed-component subset. Constraints are part of the versioned benchmark instance and must be checked deterministically.

### Generalization

The same protocol is evaluated on a collection selected specifically to reduce memorization and puzzle-family leakage. Generalization is a property of the collection/split methodology, not a different verifier.

## 5. Input representation

Benchmark puzzle inputs should normally use the deterministic model-oriented serialization derived from canonical semantic `PuzzleDefinition` state rather than opaque raw game bytes.

The serializer is versioned independently from the `PuzzleDefinition` schema. Given the same validated semantic definition and serializer version, it must emit identical content. The current contract lives in [`puzzle-serialization.md`](puzzle-serialization.md).

A benchmark result must record the serializer identity and exact semantic puzzle-definition identity so performance changes caused by representation changes are distinguishable from model changes.

Exact `.puzzle` bytes remain separate `PuzzleArtifact` evidence. They are selected only at the verification boundary for profiles that require exact-artifact verification and are not the model-facing semantic authority.

Raw `.puzzle` bytes may still be used for systems that explicitly consume the game format, but that is a different input profile and must be reported separately.

## 6. Output representation

The v0.1 Solve path uses one deterministic candidate-output boundary. Raw model output is not silently cleaned up by prompts or runner-specific heuristics.

The candidate-output compiler:

- defines the accepted response envelope;
- deterministically extracts or rejects the candidate;
- produces exact `.solution` bytes;
- has its own versioned identity;
- preserves a content hash for the exact compiled candidate used downstream.

Output compilation failure must be reported separately from verifier-side solution parse failure. Ambiguous multiple candidates, malformed framing, unsupported output forms, and other under-specified cases fail closed rather than being repaired by a reasoning agent.

Future protocol versions may define additional output profiles, but each profile must commit to one deterministic parser/compiler identity before verification.

## 7. Attempt profiles

Attempt policy is part of benchmark identity.

### One-shot

The system receives one puzzle and may submit exactly one candidate without verifier feedback.

Report at least:

- `Solve@1`;
- output-compile failure rate;
- verifier-parse failure rate;
- simulation failure rate.

### Interactive

A future bounded interactive profile may allow up to `N` submissions for one puzzle and return deterministic structured verifier feedback after failed attempts.

Report at least:

- `Solve@1`;
- `Solve@N`;
- median attempts to first success;
- verifier calls to first success;
- model calls and tokens to first success where available.

The feedback schema must be versioned. Raw implementation logs are not a stable benchmark interface.

Different feedback strengths should be separate named profiles rather than silently changing the same benchmark.

The initial exact-output v0.1 harness should stabilize the one-shot path before interactive execution becomes part of the required benchmark surface.

## 8. Correctness and failure taxonomy

Feasibility is the first scoring layer.

Each attempt ends in one stable top-level outcome:

- output compilation failure;
- solution parse failure;
- puzzle/solution mismatch;
- simulation failure;
- verifier-successful solution.

Structured compiler/verifier errors may provide more detail, but aggregate reporting retains this stable top-level taxonomy.

A puzzle is solved only when at least one allowed attempt produces a verifier-successful solution.

Puzzles excluded from the executable inventory are not failed attempts. They are protocol-ineligible instances with explicit derived exclusion reasons and must be reported separately from solve outcomes.

## 9. Quality metrics

For every successful solution, record at least the verifier-computed Opus Magnum metrics already required by the canonical corpus:

- cost;
- cycles;
- area;
- instructions.

These are intrinsically multi-objective. The benchmark should not silently collapse them into an arbitrary weighted scalar.

A standard report should therefore include feasibility first, then quality summaries over successful solutions.

Recommended quality summaries include:

- median and distribution of each metric;
- regret versus the best-known verified corpus value for each metric;
- Pareto membership against the benchmark reference set;
- frontier coverage or hypervolume for tracks that permit multiple submissions.

Reference corpus values must be described as **best known** unless global optimality is separately proven.

For a lower-is-better metric `m`, per-puzzle regret may be reported as:

```text
regret_m = (generated_m - best_known_m) / best_known_m
```

Aggregation rules must define how missing/invalid solutions are handled and must never make an unsolved puzzle look competitive through quality-only averaging.

## 10. Leaderboard ordering

A public leaderboard should preserve the two-layer nature of the task.

Recommended ordering for Solve is lexicographic:

1. higher solve rate over the declared executable inventory;
2. better declared quality summary among solved puzzles;
3. lower declared resource usage only when the benchmark profile treats efficiency as a tiebreaker.

The collection identity and executable-inventory identity must accompany any reported solve rate so missing verifier artifacts cannot silently improve or degrade comparability.

If a future benchmark publishes a scalar score, its formula must be explicit, versioned, and described as a benchmark scoring convention rather than an inherent measure of Opus Magnum solution quality.

## 11. Reference solutions and frontiers

Reference solutions come from verifier-successful canonical `SolutionArtifact` records with immutable provenance.

Derived reference sets may include:

- best-known cost solutions;
- best-known cycle solutions;
- best-known area solutions;
- best-known instruction-count solutions;
- declared Pareto frontiers;
- human-only or machine-only subsets.

All reference selection logic must be deterministic and versioned. No benchmark should depend on a hand-curated `best/` directory or a mutable leaderboard snapshot.

## 12. Public benchmark and contamination

The frozen base-game collection is useful as a stable public benchmark, but many puzzles and solutions are publicly available and may occur in training data.

A benchmark report using `base-game-2026-06-16` must therefore describe it as a **public, contamination-prone benchmark** rather than as proof of unseen-puzzle generalization.

A stronger evaluation program should use two tiers:

- **Public tier:** immutable published collections such as `base-game-2026-06-16`, useful for reproducibility, regression testing, and broad comparability.
- **Generalization tier:** separately versioned held-out custom, community, tournament, or newly selected puzzles whose reference solutions are withheld until evaluation.

Both tiers should use the same verifier and benchmark protocol where possible.

## 13. Split methodology and leakage

Train/validation/test partitions are not part of the general corpus release.

When benchmark splits are introduced, the split construction algorithm must be explicit and versioned. Random row splitting is insufficient when related puzzles or near-variants can leak structure across partitions.

Where the corpus permits it, split methodology should consider grouping by puzzle family, mechanic, molecule/transformation pattern, source lineage, or known variant relationships before assigning partitions.

The benchmark manifest must record the exact selected semantic puzzle IDs and the algorithm/version that produced them. Executable eligibility remains a separate derived projection so artifact availability does not redefine the split itself.

## 14. Resource accounting

Benchmark reports should retain useful resource measurements when available, including:

- model calls;
- input and output tokens;
- verifier calls;
- attempts;
- wall-clock time;
- optional provider cost.

Only deterministic or sufficiently controlled measurements should influence canonical benchmark ordering. Wall time and provider price are environment-dependent and should normally be reported rather than treated as correctness criteria.

Missing resource observations must remain missing rather than being silently converted to zero.

## 15. Baselines

Useful baselines may include:

- a no-op or deliberately invalid baseline to validate failure accounting;
- simple deterministic template/heuristic solvers;
- OpusSolver or other clearly identified machine-generated systems;
- best-known verified human/reference corpus solutions as quality ceilings, not as solver baselines.

Every baseline result must identify the exact system revision, harness version, benchmark version, executable inventory identity, and resource policy used.

## 16. Result schema

A benchmark run should record enough information to reproduce and audit every aggregate number.

At minimum:

```text
benchmark protocol/version
benchmark collection ID + manifest hash
executable inventory identity/hash
model/system identity
agent/harness identity and revision
semantic puzzle definition identity
input serializer version
candidate-output compiler version
selected exact puzzle artifact identity
verifier identity + revision/hash
validation profile version
attempt profile and budget
per-puzzle attempts
per-attempt failure/success status
candidate content hash
verification IDs for successful attempts
computed metrics
resource usage where available
aggregate report
```

Aggregate reports are derived from per-puzzle results and must not be maintained independently.

## 17. Determinism and reproducibility

Given identical benchmark semantic inputs, executable inventory, and recorded raw candidate outputs, re-evaluation must reproduce the same compilation, exact candidate bytes, parsing, verification, computed metrics, and aggregate report under the pinned harness.

Model generation itself need not be deterministic. The benchmark must record sampling/configuration information sufficient to interpret repeated runs, and stochastic systems should report multiple runs when variance matters.

Executable inventory derivation must itself be deterministic. Input/source ordering must not change which semantic puzzles are runnable, which exact puzzle artifact is selected, or the inventory identity.

## 18. Relationship to corpus releases

Benchmark materialization must reuse the existing corpus architecture:

```text
canonical PuzzleDefinition + artifact / verification facts
        ↓
versioned derived puzzle/reference views
        ↓
benchmark collection + protocol
        ↓
derived executable inventory
        ↓
evaluation harness
        ↓
canonical verifier
        ↓
benchmark result artifacts
```

The benchmark must not introduce a second source cache, artifact store, semantic puzzle store, verification authority, executable-membership ledger, or manually maintained solution index.

Benchmark-specific Hugging Face configs may be added later as downstream projections, but the general corpus configs and immutable collection splits remain unchanged.

## 19. v0.1 implementation scope

The first implementation should stay narrow:

- implement the exact-output Solve track;
- stabilize one-shot execution before bounded interactive evaluation;
- use the implemented deterministic `PuzzleDefinition` text serialization;
- derive the executable puzzle inventory from semantic, artifact, and verifier-ready coverage rather than requiring all collection members to have exact artifacts;
- define one deterministic candidate-output compiler from raw model output to exact `.solution` bytes;
- verify every compiled candidate through the pinned canonical verifier against the exact puzzle artifact selected by the executable inventory;
- emit the stable WP-15 attempt/per-puzzle/result taxonomy and deterministic aggregate report;
- report solve rate, failure taxonomy, exact metrics, attempts, verifier calls, and resource usage where available;
- use verifier-derived reference metrics/frontiers only as optional comparisons, not as a prerequisite for basic Solve correctness;
- exercise the public harness through a hermetic repository-owned fixture that requires no network, provider credentials, operator-owned game install, or unavailable official artifacts;
- run on the verifier-ready subset of immutable public `base-game-2026-06-16` while preserving the full semantic collection identity and explicit exclusion reasons;
- keep held-out generalization collection design as a separately versioned follow-up.

Optimization, frontier generation, repair, constrained solving, and interactive feedback should follow only after exact-output Solve has a stable candidate compiler, result schema, executable-inventory derivation, and reproducible harness.

## 20. Acceptance criteria

A benchmark protocol is ready for stable use when:

1. protocol identity commits to the collection, executable inventory, semantic serializer, candidate-output compiler, verifier, validation profile, attempt policy, and scoring/reporting rules;
2. benchmark collection membership is semantic and immutable, while verifier-ready execution eligibility is deterministically derived with explicit exclusion reasons;
3. every submitted raw candidate is preserved or content-addressed sufficiently to reproduce exact compiled candidate bytes and evaluation;
4. correctness is determined only by the pinned verifier against the selected exact puzzle artifact;
5. output compilation, solution parse, puzzle mismatch, simulation failure, and verifier success are reported distinctly;
6. quality is reported as explicit multi-objective metrics or versioned derived comparisons;
7. aggregate results can be regenerated deterministically from per-puzzle records;
8. public-benchmark contamination limitations are documented;
9. split methodology is explicit before any generalization claims are made;
10. benchmark artifacts and executable inventories remain derived from canonical corpus facts rather than becoming parallel authorities.
