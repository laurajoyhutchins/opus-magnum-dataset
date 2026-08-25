from __future__ import annotations

from copy import deepcopy

import pytest

from opus_corpus.serialization import ModelPuzzleTextSerializer, PuzzleSerializationError


def _normalized_puzzle() -> dict[str, object]:
    return {
        "normalized_puzzle_id": "normalized-puzzle-0001",
        "puzzle_id": "om.puzzle.0001",
        "puzzle_artifact_id": "puzzle-artifact-0001",
        "normalizer_version": "test-normalizer-v1",
        "allowed_parts": ["arm1", "bonder"],
        "reagents": [
            {
                "molecule_id": "reagent-0",
                "atoms": [
                    {"atom_id": "a0", "atom_type": "salt", "q": 0, "r": 0},
                    {"atom_id": "a1", "atom_type": "air", "q": 1, "r": 0},
                ],
                "bonds": [{"a": "a0", "b": "a1", "bond_type": "single"}],
            }
        ],
        "products": [
            {
                "molecule_id": "product-0",
                "atoms": [
                    {"atom_id": "a0", "atom_type": "salt", "q": 0, "r": 0},
                    {"atom_id": "a1", "atom_type": "air", "q": 1, "r": 0},
                    {"atom_id": "a2", "atom_type": "air", "q": 0, "r": 1},
                ],
                "bonds": [
                    {"a": "a0", "b": "a1", "bond_type": "single"},
                    {"a": "a0", "b": "a2", "bond_type": "single"},
                ],
            }
        ],
        "constraints": {},
    }


def test_model_puzzle_text_serializer_matches_v1_golden_output() -> None:
    serializer = ModelPuzzleTextSerializer()

    assert serializer.format_name == "opus-magnum-puzzle-text"
    assert serializer.version == "1"
    assert serializer.serialize_puzzle(_normalized_puzzle()) == (
        "OPUS_MAGNUM_PUZZLE_TEXT_V1\n"
        'puzzle_id="om.puzzle.0001"\n'
        'allowed_parts=["arm1","bonder"]\n'
        'reagents=[{"atoms":[{"atom_id":"a0","atom_type":"salt","q":0,"r":0},'
        '{"atom_id":"a1","atom_type":"air","q":1,"r":0}],"bonds":'
        '[{"a":"a0","b":"a1","bond_type":"single"}],"molecule_id":"reagent-0"}]\n'
        'products=[{"atoms":[{"atom_id":"a0","atom_type":"salt","q":0,"r":0},'
        '{"atom_id":"a1","atom_type":"air","q":1,"r":0},{"atom_id":"a2",'
        '"atom_type":"air","q":0,"r":1}],"bonds":[{"a":"a0","b":"a1",'
        '"bond_type":"single"},{"a":"a0","b":"a2","bond_type":"single"}],'
        '"molecule_id":"product-0"}]\n'
        "constraints={}\n"
    )


def test_model_puzzle_text_serializer_is_deterministic_for_mapping_order() -> None:
    serializer = ModelPuzzleTextSerializer()
    puzzle = _normalized_puzzle()
    reordered = dict(reversed(list(puzzle.items())))
    reordered["constraints"] = {"z": {"b": 2, "a": 1}, "a": True}
    puzzle["constraints"] = {"a": True, "z": {"a": 1, "b": 2}}

    assert serializer.serialize_puzzle(puzzle) == serializer.serialize_puzzle(reordered)


def test_model_puzzle_text_serializer_excludes_corpus_lineage_metadata() -> None:
    rendered = ModelPuzzleTextSerializer().serialize_puzzle(_normalized_puzzle())

    assert "normalized-puzzle-0001" not in rendered
    assert "puzzle-artifact-0001" not in rendered
    assert "test-normalizer-v1" not in rendered
    assert 'puzzle_id="om.puzzle.0001"' in rendered


def test_model_puzzle_text_serializer_json_escapes_string_content() -> None:
    puzzle = deepcopy(_normalized_puzzle())
    puzzle["reagents"][0]["atoms"][0]["atom_type"] = 'salt\n"quoted"'

    rendered = ModelPuzzleTextSerializer().serialize_puzzle(puzzle)

    assert 'salt\\n\\"quoted\\"' in rendered
    assert len(rendered.splitlines()) == 6


def test_model_puzzle_text_serializer_fails_closed_on_invalid_normalized_puzzle() -> None:
    puzzle = _normalized_puzzle()
    del puzzle["products"]

    with pytest.raises(PuzzleSerializationError, match="normalized puzzle violates schema"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)
