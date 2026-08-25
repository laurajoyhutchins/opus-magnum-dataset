from __future__ import annotations

import json
from typing import Any

import pytest

from opus_corpus.serialization import ModelPuzzleTextSerializer, PuzzleSerializationError


def _puzzle_with_constraints(constraints: dict[Any, Any]) -> dict[str, Any]:
    return {
        "normalized_puzzle_id": "normalized-puzzle-0001",
        "puzzle_id": "om.puzzle.0001",
        "puzzle_artifact_id": "puzzle-artifact-0001",
        "normalizer_version": "test-normalizer-v1",
        "allowed_parts": ["arm1"],
        "reagents": [
            {
                "molecule_id": "reagent-0",
                "atoms": [{"atom_id": "a0", "atom_type": "salt", "q": 0, "r": 0}],
                "bonds": [],
            }
        ],
        "products": [
            {
                "molecule_id": "product-0",
                "atoms": [{"atom_id": "a0", "atom_type": "salt", "q": 0, "r": 0}],
                "bonds": [],
            }
        ],
        "constraints": constraints,
    }


def test_model_puzzle_text_serializer_version_is_not_constructor_configurable() -> None:
    with pytest.raises(TypeError):
        ModelPuzzleTextSerializer(version="2")


def test_model_puzzle_text_serializer_rejects_non_finite_json_values() -> None:
    puzzle = _puzzle_with_constraints({"limit": float("nan")})

    with pytest.raises(PuzzleSerializationError, match="not canonical JSON"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)


def test_model_puzzle_text_serializer_rejects_non_string_object_keys() -> None:
    puzzle = _puzzle_with_constraints({1: "one"})

    with pytest.raises(PuzzleSerializationError, match="not canonical JSON"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)


def test_model_puzzle_text_serializer_rejects_python_only_sequence_types() -> None:
    puzzle = _puzzle_with_constraints({"limits": (1, 2)})

    with pytest.raises(PuzzleSerializationError, match="not canonical JSON"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)


def test_model_puzzle_text_serializer_rejects_non_utf8_strings() -> None:
    puzzle = _puzzle_with_constraints({"label": "\ud800"})

    with pytest.raises(PuzzleSerializationError, match="not canonical JSON"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)


def test_model_puzzle_text_serializer_escapes_unicode_line_separators() -> None:
    puzzle = _puzzle_with_constraints({"label": "a\u0085b\u2028c\u2029d"})

    rendered = ModelPuzzleTextSerializer().serialize_puzzle(puzzle)

    assert "\\u0085" in rendered
    assert "\\u2028" in rendered
    assert "\\u2029" in rendered
    assert len(rendered.splitlines()) == 6


def test_model_puzzle_text_serializer_rejects_cyclic_json_values() -> None:
    constraints: dict[str, Any] = {}
    constraints["self"] = constraints
    puzzle = _puzzle_with_constraints(constraints)

    with pytest.raises(PuzzleSerializationError, match="not canonical JSON"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)


def test_model_puzzle_text_serializer_accepts_deep_acyclic_json_values() -> None:
    nested: Any = "leaf"
    for _ in range(600):
        nested = [nested]
    constraints = {"nested": nested}

    # The encoder itself can represent this value at the interpreter's normal recursion limit.
    json.dumps(constraints, allow_nan=False, ensure_ascii=False, separators=(",", ":"))

    rendered = ModelPuzzleTextSerializer().serialize_puzzle(
        _puzzle_with_constraints(constraints)
    )

    assert rendered.startswith("OPUS_MAGNUM_PUZZLE_TEXT_V1\n")
    assert "constraints={\"nested\":" in rendered
