# WP-09 libverify Verification Design

Status: approved implementation design for WP-09.

## Goal

Implement deterministic verification of canonical `PuzzleArtifact` + `SolutionArtifact` pairs using the pinned `omsim` `libverify` API behind the existing simulator-independent `Verifier` protocol.

## Settled dependencies

WP-09 consumes the landed contracts from WP-01, WP-04, and WP-08. It does not change canonical artifact identity, acquisition, normalization, or release materialization.

The verifier source revision is the same `omsim` revision already pinned by the repository:

`758f4a4b4c9e24f50294801da774a0960c922bab`

## Architecture

Two focused modules own the packet.

`opus_corpus.libverify` owns the native boundary. `LibverifyVerifier` loads an explicitly supplied `libverify` shared library only after its SHA-256 matches an independently supplied expected digest, drives the documented byte-array verifier API, and returns the existing `VerificationResult` contract. A narrow backend protocol isolates FFI mechanics from result mapping so hermetic tests can exercise verification semantics without compiling native code.

`opus_corpus.verification_materialization` owns deterministic conversion from canonical artifact records to canonical verification records. It reads exact bytes through the existing `ContentStore`, matches each solution artifact to the unique canonical puzzle artifact for its `puzzle_id`, invokes a `Verifier`, schema-validates the returned canonical result, and returns verification records in deterministic order. It creates no second object store or verification authority.

## Verifier identity and validation profile

The implementation identity is `omsim-libverify`.

The verifier revision is the pinned `omsim` commit above. `verifier_sha256` is the SHA-256 of the exact loaded shared-library file. The native file is a separately pinned runtime input because binary bytes can depend on platform, compiler, linker, and build recipe. `LibverifyVerifier.from_library(path, expected_sha256=...)` verifies the expected digest before loading the library; ABI compatibility alone is never treated as evidence that an arbitrary binary is the pinned verifier.

Provisioning is responsible for pairing a native binary digest with the pinned source revision. Reproducing an identical verification identity requires the same native binary bytes, not merely recompiling the same source revision with an unspecified toolchain.

WP-09 defines one v1 validation profile: `omsim-libverify-v1`. The profile uses libverify's normal limits with an explicit 150,000-cycle limit and evaluates the canonical metrics `cost`, `instructions`, `cycles`, and `area` in that order. Supplying another profile fails closed before native execution.

## Parse, simulation, and metric semantics

`verifier_create_from_bytes` receives the exact puzzle and solution bytes.

If libverify reports a puzzle-file or solution-file error, the result records `parse_status = failed`, `simulation_status = not_run`, null metrics, and a stable error code (`puzzle_parse_failed` or `solution_parse_failed`). This remains true if libverify discovers a decode failure during metric evaluation after the initial byte-level parse succeeded.

Once parsing/decoding is known to be successful, metric evaluation drives simulation. A simulation or metric error during evaluation records `parse_status = passed`, `simulation_status = failed`, nulls all four authoritative metrics, and retains a stable error code plus deterministic detail. Successful evaluation records `simulation_status = passed` and the four recomputed integer metrics.

Canonical metrics are all-or-nothing in this packet. Partial values from a failed evaluation are not retained as authoritative verification metrics.

## Constructibility predicates

Simulator validity, ordinary in-game constructibility, and record eligibility are distinct concepts. libverify simulation success alone does not prove the latter two. WP-09 therefore emits `vanilla_constructible = null` and `record_eligible = null` for this profile rather than conflating them with simulator success. Later versioned predicate derivations may populate them without changing verification facts.

## Error representation

Stable codes are derived from libverify's documented error source:

- puzzle file -> `puzzle_parse_failed`
- solution file -> `solution_parse_failed`
- simulation -> `simulation_failed`
- metric -> `metric_evaluation_failed`
- unknown source -> `verifier_failed`

`error_detail` contains only deterministic libverify text and, when available for simulation failures, cycle and board coordinates. It never embeds local filesystem paths or object addresses.

## Determinism and fail-closed behavior

Repeated evaluation of identical artifact bytes, exact pinned shared-library bytes, pinned revision, and validation profile must produce identical `VerificationResult` values.

Materialization rejects missing puzzle artifacts, more than one puzzle artifact for a solution's puzzle, unsupported artifact kinds/formats, corrupt/missing content-store objects, schema-invalid verifier results, unsupported validation profiles, and native API errors. Artifact iteration order and cache-root location must not affect logical output.

## Native-library provisioning

WP-09 does not introduce a verifier download service, source cache, or vendored copy of `omsim`. The shared library is an explicit runtime input paired with an expected SHA-256 and the pinned upstream revision. The runtime factory verifies the digest before loading the binary.

The repository's upstream contract test downloads the exact source revision in CI, builds `libverify.so` with the upstream source set, hashes that just-built binary, and uses the observed digest as the expected pin for that test invocation. This proves the ctypes ABI and binary-pin enforcement path against the pinned sources without claiming cross-toolchain binary reproducibility.

## Testing

Hermetic tests cover profile rejection, expected binary-hash enforcement, success mapping, immediate and late puzzle/solution parse failures, simulation/metric failures, handle cleanup, deterministic repeated results, canonical result schema validation, artifact pairing, object integrity, and input-order independence using a scripted backend and fake verifier where appropriate.

A marked `upstream` contract builds the pinned `omsim` `libverify.so` on Linux and verifies a real upstream puzzle/solution fixture. This proves the ctypes signatures and metric names against the pinned native implementation while keeping the ordinary test suite network-free.

## Non-goals

- no source acquisition changes;
- no second content store or verifier-result store;
- no solution parser/normalizer implementation;
- no release-row projection or release-format changes;
- no claim that simulator success implies ordinary constructibility or record eligibility;
- no alternate simulator or custom simulation semantics.
