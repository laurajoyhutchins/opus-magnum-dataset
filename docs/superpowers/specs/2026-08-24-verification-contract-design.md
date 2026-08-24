# Canonical Verification Contract Design

## Status

Approved in chat as the first PR in the downstream materialization stack. This document narrows that approval into a repository-local contract before implementation.

## Goal

Introduce Verification as a first-class canonical derived entity with a deterministic identity and a narrow verifier interface, without integrating `omsim`, changing acquisition, or creating a second source-ingestion path.

## Stack position

This PR starts from current `main`, after the content-addressed cache (#6) and `om-leaderboard` acquisition (#9) have landed. It must not depend on or revive the diverged `feature/artifact-ingestion` / superseded snapshot-ingestion machinery.

The intended stack is:

```text
main with #6 + #9
  -> verification contract
    -> normalized-solution contract
      -> deterministic materialization pipeline
```

## Authority and derivation boundary

Acquired bytes and receipts remain immutable source facts. Verification is derived state computed from an exact `PuzzleArtifact` + exact `SolutionArtifact` pair under a pinned verifier implementation and validation profile.

A source claim such as leaderboard cost/cycles/area/instructions remains an Observation fact. A Verification record never overwrites that claim. Downstream release projections may place verified metrics beside solution metadata, but that flattening is a generated projection rather than canonical ownership of verification facts.

## Canonical Verification record

Add `schemas/verification.schema.json` with a strict object shape. Required fields:

- `verification_id`
- `puzzle_artifact_id`
- `solution_id`
- `verifier_implementation`
- `verifier_revision`
- `verifier_sha256`
- `validation_profile`
- `parse_status`
- `simulation_status`
- `cost`
- `cycles`
- `area`
- `instructions`
- `vanilla_constructible`
- `record_eligible`
- `error_code`
- `error_detail`

`verifier_sha256` is nullable because some verifier integrations may initially pin an immutable source revision before a standalone binary hash is practical. `cost`, `cycles`, `area`, and `instructions` are nullable when verification does not successfully produce metrics. `vanilla_constructible` and `record_eligible` are independently nullable because simulator validity, ordinary constructibility, and record eligibility are distinct predicates.

`parse_status` is one of `not_run`, `passed`, `failed`. `simulation_status` is one of `not_run`, `passed`, `failed`. `error_code` and `error_detail` are nullable strings. The schema rejects unknown fields; no arbitrary verifier-specific payload is added here.

## Deterministic identity

`verification_id` is derived only from the identity of the evaluation, not from the result. Its identity payload contains:

- `puzzle_artifact_id`
- `solution_id`
- `verifier_implementation`
- `verifier_revision`
- `verifier_sha256`
- `validation_profile`

The implementation serializes this payload with the existing `canonical_json_bytes()` helper, hashes it with SHA-256, and emits `om.verification.<hex-digest>`.

Changing computed metrics or error text must not change the verification identity. Changing the artifact pair, verifier identity, or validation profile must.

## Python interface

Add `src/opus_corpus/verification.py` containing only general verification-domain types and deterministic helpers. It must not import an adapter or simulator implementation.

The public seam is:

```python
@dataclass(frozen=True)
class VerificationInput:
    puzzle_artifact_id: str
    solution_id: str
    puzzle_bytes: bytes
    solution_bytes: bytes
    validation_profile: str

@dataclass(frozen=True)
class VerificationResult:
    verification_id: str
    puzzle_artifact_id: str
    solution_id: str
    verifier_implementation: str
    verifier_revision: str
    verifier_sha256: str | None
    validation_profile: str
    parse_status: str
    simulation_status: str
    cost: int | None
    cycles: int | None
    area: int | None
    instructions: int | None
    vanilla_constructible: bool | None
    record_eligible: bool | None
    error_code: str | None
    error_detail: str | None

class Verifier(Protocol):
    def verify(self, value: VerificationInput) -> VerificationResult: ...
```

The interface passes bytes because verification is an offline materialization step consuming pinned cached objects. It must not fetch network resources or depend on mutable upstream paths.

Add `verification_id(...) -> str` implementing the identity rule above.

## Relationship to current release schemas

Do not remove the current flattened verification fields from `schemas/solution.schema.json` in this PR. That schema is already consumed by the release pipeline. Removing those fields before the materialization bridge exists would make this seam unnecessarily invasive.

The later deterministic-materialization PR will define how canonical Verification records project into the existing solution release row. At that point the project can decide whether to retain the flattened release shape or version it.

## Tests

Add `tests/test_verification.py` proving successful and failed schema records, strict field/status validation, deterministic and change-sensitive IDs, exclusion of result fields from ID generation, and a fake simulator-independent verifier satisfying the protocol.

## Non-goals

No `omsim`/`libverify` integration, solution parsing, acquisition changes, normalization, release materialization, retry/orchestration machinery, cache changes, database, or maintained verification index.

## Acceptance criteria

The verification schema, protocol/data types, deterministic ID helper, and focused contract tests exist; full repository validation passes; and no simulator-specific or acquisition-specific code is introduced.
