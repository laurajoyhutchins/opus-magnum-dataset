# Deterministic verification

The corpus verifies exact canonical puzzle and solution artifacts through the simulator-independent `Verifier` contract in `opus_corpus.verification`. The v1 implementation is `LibverifyVerifier` in `opus_corpus.libverify`, backed by the upstream `omsim` `libverify` FFI.

## Pinned implementation identity

The v1 verifier identity is:

- implementation: `omsim-libverify`;
- source revision: `758f4a4b4c9e24f50294801da774a0960c922bab`;
- validation profile: `omsim-libverify-v1`;
- cycle limit: `150000`;
- authoritative metrics: `cost`, `instructions`, `cycles`, and `area`.

The revision is the same immutable `omsim` revision already used by the repository's source adapter. The exact native shared library is supplied explicitly at runtime. `LibverifyVerifier.from_library(path)` hashes that file and records its SHA-256 as `verifier_sha256`, so a verification identity includes both source revision/profile identity and evidence for the exact native binary that executed it.

The repository does not create a second downloader, source cache, or object store for the verifier. Building or provisioning `libverify` is a runtime concern. Canonical puzzle and solution bytes continue to come only from the existing artifact/content-store path.

## Native boundary

`CtypesLibverifyBackend` binds the documented byte-array FFI rather than staging temporary `.puzzle` or `.solution` files. It passes exact byte buffers with explicit lengths to `verifier_create_from_bytes`, sets the profile's cycle limit, evaluates the four canonical integer metrics, reads structured verifier errors, and always destroys the native verifier handle.

The upstream contract test downloads the exact pinned `omsim` revision, compiles `libverify.so` from the upstream C sources, and verifies a matching upstream puzzle/solution fixture through the production ctypes adapter. Ordinary pytest remains network-free; the native contract runs under the repository's explicit `upstream` CI phase.

## Canonical result semantics

A successful native parse followed by successful metric evaluation produces:

- `parse_status = passed`;
- `simulation_status = passed`;
- recomputed `cost`, `instructions`, `cycles`, and `area`;
- no error code or detail.

Source-declared leaderboard or archive metrics are observations only. They are never promoted into canonical verification metrics.

An immediate puzzle-file or solution-file error is retained as a canonical failed attempt with `parse_status = failed`, `simulation_status = not_run`, null metrics, and a stable code:

- puzzle-file error: `puzzle_parse_failed`;
- solution-file error: `solution_parse_failed`.

An error raised while evaluating metrics retains `parse_status = passed`, sets `simulation_status = failed`, nulls all four canonical metrics, and records one of:

- simulation error: `simulation_failed`;
- metric error: `metric_evaluation_failed`;
- unrecognized native error source: `verifier_failed`.

`error_detail` preserves deterministic upstream error text and includes cycle/board coordinates when libverify reports a nonzero error cycle. Partial metric values observed before a failed evaluation are not canonical facts.

## Constructibility and record predicates

Simulator success, ordinary in-game constructibility, and record eligibility are separate claims. The v1 libverify profile establishes simulator validity and recomputed metrics only. It therefore leaves `vanilla_constructible` and `record_eligible` as null rather than inferring either predicate from simulation success.

Future deterministic, versioned predicate implementations may populate those fields without changing the meaning of the v1 verification facts.

## Artifact materialization boundary

`materialize_verifications()` in `opus_corpus.verification_materialization` consumes canonical `ArtifactRecord` values from the landed puzzle and solution materializers plus the existing `ContentStore`.

For every solution artifact it:

1. requires exactly one canonical puzzle artifact with the same `puzzle_id`;
2. validates canonical artifact kind, format, content-derived ID, object key, byte length, and SHA-256;
3. reads the exact puzzle and solution bytes through the shared content store;
4. invokes the supplied `Verifier` with those exact bytes and artifact identities;
5. validates returned artifact lineage and validation-profile identity;
6. returns canonical verification records sorted by `verification_id`.

Missing or corrupt objects, ambiguous puzzle identities, malformed artifact records, conflicting duplicate artifact facts, wrong verifier lineage, and duplicate verification identities fail closed. Artifact input order and content-store root location do not affect logical output.

## Determinism boundary

For identical puzzle bytes, solution bytes, canonical artifact identities, verifier implementation/revision, exact native binary hash, and validation profile, repeated verification produces the same `VerificationResult` and `verification_id`.

Changing the verifier binary, pinned source revision, validation profile, or either artifact identity creates a different verification identity rather than silently overwriting prior facts.
