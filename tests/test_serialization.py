from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def _normalized_puzzle() -> dict[str, object]:
    return {
        "normalized_puzzle_id": "normalized-puzzle-0001",
        "puzzle_id": "om.puzzle.0001",
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


def test_normalized_puzzle_schema_accepts_molecular_structure():
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "schemas" / "normalized-puzzle.schema.json"
    assert schema_path.is_file(), "normalized puzzle schema is missing"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(_normalized_puzzle()))
    assert errors == []


def test_normalized_puzzle_schema_excludes_source_provenance():
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "schemas" / "normalized-puzzle.schema.json"
    assert schema_path.is_file(), "normalized puzzle schema is missing"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    row = _normalized_puzzle() | {"source_uri": "https://example.invalid/source"}
    errors = list(Draft202012Validator(schema).iter_errors(row))
    assert errors


def test_canonical_json_serializer_is_deterministic_for_puzzles():
    from opus_corpus.serialization import CanonicalJsonSerializer

    serializer = CanonicalJsonSerializer()
    puzzle = _normalized_puzzle()
    reversed_keys = dict(reversed(list(puzzle.items())))
    assert serializer.serialize_puzzle(puzzle) == serializer.serialize_puzzle(reversed_keys)
    assert serializer.format_name == "canonical-json"
    assert serializer.version == "1"


def test_serializer_interface_covers_puzzles_and_solutions():
    from opus_corpus.serialization import CanonicalJsonSerializer, NormalizedSerializer

    serializer = CanonicalJsonSerializer()
    assert isinstance(serializer, NormalizedSerializer)
    assert serializer.serialize_puzzle(_normalized_puzzle()).startswith("{")
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
