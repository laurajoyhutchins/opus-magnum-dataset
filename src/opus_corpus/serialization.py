from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from jsonschema import Draft202012Validator

from .errors import CorpusError
from .hashing import canonical_json_bytes
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
        return canonical_json_bytes(puzzle).decode("utf-8")

    def serialize_solution(self, solution: NormalizedRecord) -> str:
        return canonical_json_bytes(solution).decode("utf-8")


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
        _validate_model_json_value(value)
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        encoded = _escape_model_line_separators(encoded)
        encoded.encode("utf-8")
        return encoded
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise PuzzleSerializationError(
            "normalized puzzle contains a value that is not canonical JSON"
        ) from exc


def _validate_model_json_value(value: Any) -> None:
    active_container_ids: set[int] = set()
    stack: list[tuple[bool, Any]] = [(False, value)]

    while stack:
        exiting_container, current = stack.pop()
        if exiting_container:
            active_container_ids.remove(id(current))
            continue

        value_type = type(current)
        if current is None or value_type in {bool, int, float}:
            continue
        if value_type is str:
            _validate_model_json_string(current)
            continue
        if value_type not in {list, dict}:
            _raise_noncanonical_json()

        container_id = id(current)
        if container_id in active_container_ids:
            _raise_noncanonical_json()
        active_container_ids.add(container_id)
        stack.append((True, current))

        if value_type is list:
            for item in reversed(current):
                stack.append((False, item))
            continue

        for key, item in current.items():
            if type(key) is not str:
                _raise_noncanonical_json()
            _validate_model_json_string(key)
            stack.append((False, item))


def _validate_model_json_string(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PuzzleSerializationError(
            "normalized puzzle contains a value that is not canonical JSON"
        ) from exc


def _escape_model_line_separators(value: str) -> str:
    return (
        value.replace("\u0085", "\\u0085")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _raise_noncanonical_json() -> None:
    raise PuzzleSerializationError(
        "normalized puzzle contains a value that is not canonical JSON"
    )
