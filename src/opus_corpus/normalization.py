from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .hashing import canonical_json_bytes, sha256_bytes

NormalizedSolutionRecord = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SolutionNormalizationInput:
    solution_id: str
    puzzle_id: str
    solution_bytes: bytes


@runtime_checkable
class SolutionNormalizer(Protocol):
    version: str

    def normalize(self, value: SolutionNormalizationInput) -> NormalizedSolutionRecord: ...


def normalized_solution_id(
    *,
    solution_id: str,
    puzzle_id: str,
    normalizer_version: str,
) -> str:
    identity = {
        "solution_id": solution_id,
        "puzzle_id": puzzle_id,
        "normalizer_version": normalizer_version,
    }
    digest = sha256_bytes(canonical_json_bytes(identity))
    return f"om.normalized-solution.{digest}"
