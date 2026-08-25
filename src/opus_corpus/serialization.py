from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from jsonschema import Draft202012Validator

from .errors import CorpusError
from .schema_resources import load_schema_resource

NormalizedRecord = Mapping[str, Any]


@runtime_checkable
class NormalizedPuzzleSerializer(Protocol):
    """Serializer contract for derived normalized puzzle records."""

    format_name: str
    version: str

    def serialize_puzzle(self, puzzle: NormalizedRecord) -> str: ...


@runtime_checkable
class NormalizedSerializer(NormalizedPuzzleSerializer, Protocol):
    """Serializer contract for derived normalized puzzle and solution records."""

    def serialize_solution(self, solution: NormalizedRecord) -> str: ...


class PuzzleSerializationError(CorpusError):
    """Raised when a normalized puzzle cannot be serialized safely."""


@dataclass(frozen=True, slots=True)
class CanonicalJsonSerializer:
    """Deterministic baseline serializer for normalized records."""

    format_name: str = "canonical-json"
    version: str = "1"

    def serialize_puzzle(self, puzzle: NormalizedRecord) -> str:
        return _canonical_json(puzzle)

    def serialize_solution(self, solution: NormalizedRecord) -> str:
        return _canonical_json(solution)


class ModelPuzzleTextSerializer:
    """Versioned model-oriented text projection of a normalized puzzle."""

    __slots__ = ()

    format_name = "opus-magnum-puzzle-text"
    version = "1"

    def serialize_puzzle(self, puzzle: NormalizedRecord) -> str:
        _validate_normalized_puzzle(puzzle)
        fields = (
            ("puzzle_id", puzzle["puzzle_id"]),
            ("allowed_parts", puzzle["allowed_parts"]),
            ("reagents", puzzle["reagents"]),
            ("products", puzzle["products"]),
            ("constraints", puzzle["constraints"]),
        )
        lines = [f"OPUS_MAGNUM_PUZZLE_TEXT_V{self.version}"]
        lines.extend(f"{name}={_model_json_value(value)}" for name, value in fields)
        return "\n".join(lines) + "\n"


def _validate_normalized_puzzle(puzzle: NormalizedRecord) -> None:
    schema = load_schema_resource("normalized-puzzle.schema.json").schema
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(puzzle),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise PuzzleSerializationError(f"normalized puzzle violates schema: {detail}")


def _model_json_value(value: Any) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise PuzzleSerializationError(
            "normalized puzzle contains a value that is not canonical JSON"
        ) from exc


def _canonical_json(record: NormalizedRecord) -> str:
    return _canonical_json_value(record)


def _canonical_json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
