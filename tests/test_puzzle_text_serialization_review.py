from __future__ import annotations

import pytest

from opus_corpus.serialization import ModelPuzzleTextSerializer, PuzzleSerializationError


def test_model_puzzle_text_serializer_version_is_not_constructor_configurable() -> None:
    with pytest.raises(TypeError):
        ModelPuzzleTextSerializer(version="2")


def test_model_puzzle_text_serializer_rejects_non_finite_json_values() -> None:
    puzzle = {
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
        "constraints": {"limit": float("nan")},
    }

    with pytest.raises(PuzzleSerializationError, match="not canonical JSON"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)
