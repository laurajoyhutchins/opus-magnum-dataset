from __future__ import annotations

import pytest

from opus_corpus.puzzle_definition import build_puzzle_definition
from opus_corpus.serialization import ModelPuzzleTextSerializer, PuzzleSerializationError


def _puzzle_definition(*, atom_type: str = "salt") -> dict[str, object]:
    return build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics={
            "allowed_parts": ["bonder", "arm1"],
            "allowed_instructions": ["rotate", "grab"],
            "reagents": [
                {
                    "atoms": [
                        {"atom_type": atom_type, "q": 0, "r": 0},
                        {"atom_type": "air", "q": 1, "r": 0},
                    ],
                    "bonds": [
                        {
                            "a_q": 0,
                            "a_r": 0,
                            "b_q": 1,
                            "b_r": 0,
                            "bond_types": ["normal"],
                        }
                    ],
                }
            ],
            "products": [
                {
                    "atoms": [
                        {"atom_type": "salt", "q": 0, "r": 0},
                        {"atom_type": "air", "q": 1, "r": 0},
                        {"atom_type": "air", "q": 0, "r": 1},
                    ],
                    "bonds": [
                        {
                            "a_q": 0,
                            "a_r": 0,
                            "b_q": 1,
                            "b_r": 0,
                            "bond_types": ["normal"],
                        },
                        {
                            "a_q": 0,
                            "a_r": 0,
                            "b_q": 0,
                            "b_r": 1,
                            "bond_types": ["normal"],
                        },
                    ],
                }
            ],
            "output_scale": 1,
            "target_output_count": 6,
            "production": False,
            "production_constraints": None,
        },
        source_observation_ids=["observation-0001"],
        puzzle_artifact_ids=["om.puzzle-artifact.sha256." + "a" * 64],
    )


def test_model_puzzle_text_serializer_matches_v2_semantic_projection() -> None:
    serializer = ModelPuzzleTextSerializer()
    definition = _puzzle_definition()

    rendered = serializer.serialize_puzzle(definition)
    assert serializer.format_name == "opus-magnum-puzzle-text"
    assert serializer.version == "2"
    assert rendered.startswith(
        "OPUS_MAGNUM_PUZZLE_TEXT_V2\n"
        f'puzzle_definition_id="{definition["puzzle_definition_id"]}"\n'
        'puzzle_id="om.puzzle.0001"\n'
        'allowed_parts=["arm1","bonder"]\n'
        'allowed_instructions=["grab","rotate"]\n'
    )
    assert "output_scale=1\n" in rendered
    assert "target_output_count=6\n" in rendered
    assert "production=false\n" in rendered
    assert rendered.endswith("production_constraints=null\n")


def test_model_puzzle_text_serializer_is_deterministic_for_mapping_order() -> None:
    serializer = ModelPuzzleTextSerializer()
    puzzle = _puzzle_definition()
    reordered = dict(reversed(list(puzzle.items())))

    assert serializer.serialize_puzzle(puzzle) == serializer.serialize_puzzle(reordered)


def test_model_puzzle_text_serializer_excludes_provenance_lineage_metadata() -> None:
    rendered = ModelPuzzleTextSerializer().serialize_puzzle(_puzzle_definition())

    assert "observation-0001" not in rendered
    assert "om.puzzle-artifact.sha256." not in rendered
    assert 'puzzle_id="om.puzzle.0001"' in rendered


def test_model_puzzle_text_serializer_json_escapes_string_content() -> None:
    rendered = ModelPuzzleTextSerializer().serialize_puzzle(
        _puzzle_definition(atom_type='salt\n"quoted"')
    )

    assert 'salt\\n\\"quoted\\"' in rendered
    assert len(rendered.splitlines()) == 11


def test_model_puzzle_text_serializer_escapes_unicode_line_separators() -> None:
    rendered = ModelPuzzleTextSerializer().serialize_puzzle(
        _puzzle_definition(atom_type="salt\u0085\u2028\u2029")
    )

    assert "\\u0085" in rendered
    assert "\\u2028" in rendered
    assert "\\u2029" in rendered
    assert len(rendered.splitlines()) == 11


def test_model_puzzle_text_serializer_version_is_not_constructor_configurable() -> None:
    with pytest.raises(TypeError):
        ModelPuzzleTextSerializer(version="3")


def test_model_puzzle_text_serializer_fails_closed_on_invalid_definition() -> None:
    puzzle = _puzzle_definition()
    del puzzle["products"]

    with pytest.raises(PuzzleSerializationError, match="invalid puzzle definition"):
        ModelPuzzleTextSerializer().serialize_puzzle(puzzle)
