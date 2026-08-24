# Benchmark Protocol

Status: **Draft v0.1**

This document defines how the Opus Magnum corpus can become a reproducible benchmark without turning benchmark results, benchmark selections, or model-specific representations into new authorities.

The benchmark is a deterministic projection over the canonical corpus. A benchmark version fixes the protocol, collection, serialization, verifier, validation profile, attempt policy, and scoring/reporting rules used to evaluate a system.

## 1. Benchmark boundary

The core evaluation loop is:

```text
immutable puzzle collection
        ↓
versioned puzzle serialization
        ↓
model / solver / agent
        ↓
candidate solution representation
        ↓
deterministic parser / compiler
        ↓
exact solution artifact
        ↓
pinned verifier + validation profile
        ↓
validity + computed metrics + structured failure
        ↓
versioned benchmark report
```

The benchmark does not trust model-declared scores, filenames, source metadata, or natural-language claims of correctness. A submitted solution is successful only when it passes the pinned verifier under the benchmark's declared validation profile.

The canonical corpus remains the source of puzzle identity, artifact provenance, reference solutions, verifier evidence, and derived reference frontiers. Benchmark inputs and reports are derived state.

## 2. Protocol and collection are separate

A benchmark protocol and a benchmark collection are distinct versioned objects.

The **protocol** defines:

- accepted puzzle input representation;
- accepted solution output representation;
- verifier and validation semantics;
- attempt budget and feedback policy;
- resource accounting;
- metrics and aggregation rules;
- result schema.

The **collection** defines the immutable puzzle identities to evaluate.

This separation allows the same protocol to run against `base-game-2026-06-16`, a held-out community collection, or a future official collection without redefining benchmark semantics.

A benchmark identity should therefore commit to at least:

```text
protocol version
collection ID + manifest hash
puzzle serializer version
solution parser/compiler version
verifier identity + hash/revision
validation profile version
attempt policy
scoring/reporting version
```

## 3. Initial benchmark track: Solve

The first benchmark track should be **Solve**.

Input:

- one puzzle from an immutable benchmark collection;
- a versioned deterministic puzzle serialization;
- no reference solution.

Output:

- one candidate solution, either as exact `.solution` bytes or through a benchmark-defined textual/structured solution representation that deterministically compiles to an exact solution artifact.

Success:

- puzzle input parses;
- candidate output parses or compiles;
- the pinned verifier successfully simulates the candidate;
- required deterministic metrics are produced.

The primary benchmark question is therefore simple: **Can the evaluated system produce a verifier-successful Opus Magnum machine for this puzzle under the declared attempt policy?**

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

Benchmark puzzle inputs should normally use a deterministic model-oriented serialization derived from the canonical normalized puzzle representation rather than opaque raw game bytes.

The serializer must be versioned separately from the normalized-puzzle schema. Given the same normalized puzzle record and serializer version, it must emit identical content.

A benchmark result must record the serializer version so performance changes caused by representation changes are distinguishable from model changes.

Raw `.puzzle` bytes may still be used for systems that explicitly consume the game format, but that is a different input profile and must be reported separately.

## 6. Output representation

The benchmark should support two output profiles when useful:

1. **Exact artifact output:** the system emits valid `.solution` bytes directly.
2. **Structured output:** the system emits a benchmark-defined textual or structured solution representation that is deterministically parsed and compiled into exact `.solution` bytes before verification.

The parser/compiler is part of the benchmark harness and is versioned. Output syntax failure must be reported separately from verifier parse or simulation failure.

This separation prevents serialization trivia from being mistaken for puzzle-solving ability while still keeping the final correctness gate exact and executable.

## 7. Attempt profiles

Attempt policy is part of benchmark identity.

### One-shot

The system receives one puzzle and may submit exactly one candidate without verifier feedback.

Report at least:

- `Solve@1`;
- output-parse failure rate;
- verifier-parse failure rate;
- simulation failure rate.

### Interactive

The system may make up to `N` submissions for one puzzle and receives deterministic structured verifier feedback after failed attempts.

Report at least:

- `Solve@1`;
- `Solve@N`;
- median attempts to first success;
- verifier calls to first success;
- model calls and tokens to first success where available.

The feedback schema must be versioned. Raw implementation logs are not a stable benchmark interface.

Different feedback strengths should be separate named profiles rather than silently changing the same benchmark.

## 8. Correctness and failure taxonomy

Feasibility is the first scoring layer.

Each attempt should end in one of a small set of canonical outcomes, including:

- output syntax/compile failure;
- solution parse failure;
- puzzle/solution mismatch;
- simulation failure;
- verifier-successful solution.

Structured verifier errors may provide more detail, but aggregate reporting should retain this stable top-level taxonomy.

A puzzle is solved only when at least one allowed attempt produces a verifier-successful solution.

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

1. higher solve rate;
2. better declared quality summary among solved puzzles;
3. lower declared resource usage only when the benchmark profile treats efficiency as a tiebreaker.

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

The benchmark manifest must record the exact selected puzzle IDs and the algorithm/version that produced them.

## 14. Resource accounting

Benchmark reports should retain useful resource measurements when available, including:

- model calls;
- input and output tokens;
- verifier calls;
- attempts;
- wall-clock time;
- optional provider cost.

Only deterministic or sufficiently controlled measurements should influence canonical benchmark ordering. Wall time and provider price are environment-dependent and should normally be reported rather than treated as correctness criteria.

## 15. Baselines

Useful baselines may include:

- a no-op or deliberately invalid baseline to validate failure accounting;
- simple deterministic template/heuristic solvers;
- OpusSolver or other clearly identified machine-generated systems;
- best-known verified human/reference corpus solutions as quality ceilings, not as solver baselines.

Every baseline result must identify the exact system revision, harness version, benchmark version, and resource policy used.

## 16. Result schema

A benchmark run should record enough information to reproduce and audit every aggregate number.

At minimum:

```text
benchmark protocol/version
benchmark collection ID + manifest hash
model/system identity
agent/harness identity and revision
input serializer version
output parser/compiler version
verifier identity + revision/hash
validation profile version
attempt profile and budget
per-puzzle attempts
per-attempt failure/success status
verification IDs for successful attempts
computed metrics
resource usage where available
aggregate report
```

Aggregate reports are derived from per-puzzle results and must not be maintained independently.

## 17. Determinism and reproducibility

Given identical benchmark inputs and recorded candidate outputs, re-evaluation must reproduce the same parsing, verification, computed metrics, and aggregate report under the pinned harness.

Model generation itself need not be deterministic. The benchmark must record sampling/configuration information sufficient to interpret repeated runs, and stochastic systems should report multiple runs when variance matters.

## 18. Relationship to corpus releases

Benchmark materialization must reuse the existing corpus architecture:

```text
canonical corpus facts
        ↓
versioned derived puzzle/reference views
        ↓
benchmark collection + protocol
        ↓
evaluation harness
        ↓
canonical verifier
        ↓
benchmark result artifacts
```

The benchmark must not introduce a second source cache, artifact store, verification authority, or manually maintained solution index.

Benchmark-specific Hugging Face configs may be added later as downstream projections, but the general corpus configs and immutable collection splits remain unchanged.

## 19. v0.1 implementation scope

The first implementation should stay narrow:

- implement the Solve track;
- support one-shot and one bounded interactive profile;
- use one deterministic normalized-puzzle text serialization;
- support one exact or structured solution output path;
- verify every candidate through the pinned canonical verifier;
- report solve rate, failure taxonomy, exact metrics, best-known regret, attempts, verifier calls, and token usage where available;
- run first on the immutable public `base-game-2026-06-16` collection;
- keep held-out generalization collection design as a separately versioned follow-up.

Optimization, frontier generation, repair, and constrained tracks should follow only after Solve has a stable result schema and reproducible harness.

## 20. Acceptance criteria

A benchmark protocol is ready for stable use when:

1. protocol identity commits to the collection, serializer, output parser/compiler, verifier, validation profile, attempt policy, and scoring/reporting rules;
2. every submitted candidate is preserved or content-addressed sufficiently to reproduce its evaluation;
3. correctness is determined only by the pinned verifier;
4. parse, simulation, and success outcomes are reported distinctly;
5. quality is reported as explicit multi-objective metrics or versioned derived comparisons;
6. aggregate results can be regenerated deterministically from per-puzzle records;
7. public-benchmark contamination limitations are documented;
8. split methodology is explicit before any generalization claims are made;
9. benchmark artifacts remain derived from canonical corpus facts rather than becoming a parallel corpus authority.
