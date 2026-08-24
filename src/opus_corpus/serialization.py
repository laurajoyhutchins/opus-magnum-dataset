from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

NormalizedRecord = Mapping[str, Any]


@runtime_checkable
class NormalizedSerializer(Protocol):
    """Serializer contract for derived normalized puzzle and solution records."""

    format_name: str
    version: str

    def serialize_puzzle(self, puzzle: NormalizedRecord) -> str: ...

    def serialize_solution(self, solution: NormalizedRecord) -> str: ...


@dataclass(frozen=True, slots=True)
class CanonicalJsonSerializer:
    """Deterministic baseline serializer for normalized records."""

    format_name: str = "canonical-json"
    version: str = "1"

    def serialize_puzzle(self, puzzle: NormalizedRecord) -> str:
        return _canonical_json(puzzle)

    def serialize_solution(self, solution: NormalizedRecord) -> str:
        return _canonical_json(solution)


def _canonical_json(record: NormalizedRecord) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
