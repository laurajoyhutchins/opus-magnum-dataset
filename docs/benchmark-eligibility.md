# Benchmark eligibility projection

Status: **v1 contract for exact-output Solve v0.1**

Benchmark eligibility is derived state. It does not create a benchmark-membership ledger, a second puzzle authority, or a checked-in runnable-puzzle list.

The v1 projection consumes four existing authoritative fact sets:

- immutable collection membership and puzzle type;
- canonical `PuzzleDefinition` records;
- canonical exact `PuzzleArtifact` records;
- artifact provenance identifying the source observations that expose those exact bytes.

For every collection puzzle it reports semantic coverage, exact-artifact coverage, verifier readiness, eligibility, and a stable exclusion reason when the puzzle is not executable.

## Exclusion reasons

The v1 precedence is:

1. `missing_semantic_definition`
2. `missing_exact_artifact`
3. `no_verifier_usable_artifact`
4. `protocol_incompatible`

This keeps semantic knowledge distinct from byte availability. A puzzle with a complete semantic definition but no exact artifact remains semantically covered while being ineligible for exact-output verification.

An exact artifact is verifier-usable when it is a canonical `puzzle` artifact in `.puzzle` format with artifact-role provenance bound to its exact SHA-256. Eligibility derivation never synthesizes missing bytes.

## Artifact selection

When more than one verifier-usable exact artifact exists for a puzzle, selection is deterministic. v1 ranks source evidence in this order:

1. `official-game`
2. `omsim`
3. other canonical sources

Artifact ID is the deterministic tie-breaker within the same source rank. Input ordering and provenance observation ordering therefore cannot change the selected artifact.

The executable entry retains the selected artifact identity, SHA-256, byte length, content-store object key, rights status, and sorted source IDs. Those fields are evidence for verification; they do not become semantic puzzle authority.

## Executable inventory identity

The projection derives an executable-inventory SHA-256 and identity from the protocol/profile version, collection identity/hash, eligible puzzle identities, semantic definition identities, selected verifier artifact identities, exact artifact hashes, and selection provenance.

Changing executable membership or the selected verifier artifact changes the inventory identity. The projection itself can be canonically serialized with `benchmark_eligibility_bytes`, so the same canonical facts always produce byte-identical output.

The v0.1 Solve harness consumes this projection directly. It must not duplicate coverage logic or maintain an independent allow/deny list.