from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .hashing import canonical_json_bytes, sha256_bytes


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


def verification_id(
    *,
    puzzle_artifact_id: str,
    solution_id: str,
    verifier_implementation: str,
    verifier_revision: str,
    verifier_sha256: str | None,
    validation_profile: str,
) -> str:
    identity = {
        "puzzle_artifact_id": puzzle_artifact_id,
        "solution_id": solution_id,
        "verifier_implementation": verifier_implementation,
        "verifier_revision": verifier_revision,
        "verifier_sha256": verifier_sha256,
        "validation_profile": validation_profile,
    }
    digest = sha256_bytes(canonical_json_bytes(identity))
    return f"om.verification.{digest}"
