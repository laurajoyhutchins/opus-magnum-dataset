from __future__ import annotations

from jsonschema import Draft202012Validator

from opus_corpus.puzzle_definition import build_puzzle_definition
from opus_corpus.schema_resources import load_schema_resource


def _puzzle_definition() -> dict[str, object]:
    return build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics={
            "allowed_parts": ["arm1", "bonder"],
            "allowed_instructions": ["grab", "rotate"],
            "reagents": [
                {
                    "atoms": [
                        {"atom_type": "salt", "q": 0, "r": 0},
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
        puzzle_artifact_ids=[],
    )


def _puzzle_definition_schema() -> dict[str, object]:
    return load_schema_resource("puzzle-definition.schema.json").schema


def test_puzzle_definition_schema_accepts_semantic_molecular_structure():
    schema = _puzzle_definition_schema()
    errors = list(Draft202012Validator(schema).iter_errors(_puzzle_definition()))
    assert errors == []


def test_puzzle_definition_schema_excludes_unmodeled_source_fields():
    schema = _puzzle_definition_schema()
    row = _puzzle_definition() | {"source_uri": "https://example.invalid/source"}
    errors = list(Draft202012Validator(schema).iter_errors(row))
    assert errors


def test_puzzle_definition_schema_does_not_require_exact_artifact_identity():
    schema = _puzzle_definition_schema()
    assert "puzzle_artifact_id" not in schema["required"]
    assert "puzzle_artifact_id" not in schema["properties"]
    assert _puzzle_definition()["puzzle_artifact_ids"] == []


def test_canonical_json_serializer_is_deterministic_for_puzzles():
    from opus_corpus.serialization import CanonicalJsonSerializer

    serializer = CanonicalJsonSerializer()
    puzzle = _puzzle_definition()
    reversed_keys = dict(reversed(list(puzzle.items())))
    assert serializer.serialize_puzzle(puzzle) == serializer.serialize_puzzle(reversed_keys)
    assert serializer.format_name == "canonical-json"
    assert serializer.version == "1"


def test_serializer_interface_covers_puzzles_and_solutions():
    from opus_corpus.serialization import CanonicalJsonSerializer, CorpusSerializer

    serializer = CanonicalJsonSerializer()
    assert isinstance(serializer, CorpusSerializer)
    assert serializer.serialize_puzzle(_puzzle_definition()).startswith("{")
    assert serializer.serialize_solution(
        {
            "normalized_solution_id": "normalized-0001",
            "solution_id": "solution-0001",
            "puzzle_id": "om.puzzle.0001",
            "normalizer_version": "test-normalizer-v1",
            "parts": [],
            "tracks": [],
            "programs": [],
            "summaries": {},
        }
    ).startswith("{")
