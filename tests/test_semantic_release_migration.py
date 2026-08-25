from __future__ import annotations

from dataclasses import fields

from jsonschema import Draft202012Validator

from opus_corpus.puzzle_definition import build_puzzle_definition
from opus_corpus.puzzle_materialization import PuzzleCoverage
from opus_corpus.release_inputs import load_schema
from opus_corpus.serialization import ModelPuzzleTextSerializer


def _semantics() -> dict[str, object]:
    molecule = {
        "atoms": [{"atom_type": "salt", "q": 0, "r": 0}],
        "bonds": [],
    }
    return {
        "allowed_parts": ["arm1", "bonder"],
        "allowed_instructions": ["grab", "drop"],
        "reagents": [molecule],
        "products": [molecule],
        "output_scale": 1,
        "target_output_count": 6,
        "production": False,
        "production_constraints": None,
    }


def _definition() -> dict[str, object]:
    return build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics=_semantics(),
        source_observation_ids=("observation-1",),
        puzzle_artifact_ids=(),
    )


def test_puzzle_coverage_names_three_distinct_axes() -> None:
    assert {field.name for field in fields(PuzzleCoverage)} == {
        "puzzle_id",
        "puzzle_definition_id",
        "artifact_ids",
        "semantic_source_ids",
        "exact_source_ids",
        "semantic_covered",
        "artifact_covered",
        "verifier_ready",
    }


def test_release_puzzle_schema_is_semantic_and_does_not_require_binary_payload() -> None:
    definition = _definition()
    row = {
        **definition,
        "display_name": "Alpha Puzzle",
        "kind": "campaign",
        "aliases": [{"system": "game_puzzle_id", "value": "P001"}],
        "collection_id": "fixture",
    }

    validator = Draft202012Validator(load_schema("puzzles"))
    errors = sorted(validator.iter_errors(row), key=lambda error: list(error.path))

    assert errors == []
    assert "canonical_puzzle_artifact_id" not in row
    assert "puzzle_sha256" not in row
    assert "puzzle_bytes" not in row
    assert "rights_status" not in row


def test_model_puzzle_text_serializer_consumes_puzzle_definition() -> None:
    rendered = ModelPuzzleTextSerializer().serialize_puzzle(_definition())

    assert rendered.startswith("OPUS_MAGNUM_PUZZLE_TEXT_V2\n")
    assert 'puzzle_id="om.puzzle.0001"\n' in rendered
    assert 'allowed_instructions=["drop","grab"]\n' in rendered
    assert "output_scale=1\n" in rendered
    assert "target_output_count=6\n" in rendered
    assert "production=false\n" in rendered
    assert "production_constraints=null\n" in rendered
    assert "puzzle_artifact" not in rendered
    assert "source_observation" not in rendered
