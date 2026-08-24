from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path("schemas/normalized.schema.json")


def jsonschema_module() -> Any:
    return importlib.import_module("jsonschema")


def normalization_module() -> Any:
    return importlib.import_module("opus_corpus.normalization")


def schema_validator() -> Any:
    jsonschema = jsonschema_module()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def normalized_record() -> dict[str, Any]:
    return {
        "normalized_solution_id": "om.normalized-solution." + "a" * 64,
        "solution_id": "om.solution." + "b" * 64,
        "puzzle_id": "om.puzzle.0001",
        "normalizer_version": "fixture-v1",
        "parts": [
            {
                "part_id": "arm-1",
                "type": "arm1",
                "x": 0,
                "y": 0,
                "rotation": 0,
                "parameters": {},
            }
        ],
        "tracks": [
            {
                "track_id": "track-1",
                "coordinates": [
                    {"x": 1, "y": 0},
                    {"x": 2, "y": 0},
                ],
            }
        ],
        "programs": [
            {
                "arm_id": "arm-1",
                "instructions": [{"cycle": 0, "opcode": "grab"}],
            }
        ],
        "summaries": {
            "part_count": 1,
            "track_count": 1,
            "track_hex_count": 2,
            "program_count": 1,
            "instruction_count": 1,
            "part_type_histogram": {"arm1": 1},
            "opcode_histogram": {"grab": 1},
        },
    }


def assert_schema_rejects(record: dict[str, Any]) -> None:
    validation_error = jsonschema_module().ValidationError
    try:
        schema_validator().validate(record)
    except validation_error:
        return
    raise AssertionError("normalized solution schema unexpectedly accepted invalid record")


def test_normalized_solution_schema_accepts_structural_record():
    schema_validator().validate(normalized_record())


def test_normalized_solution_schema_rejects_unknown_part_fields():
    record = normalized_record()
    record["parts"][0]["mystery"] = 1
    assert_schema_rejects(record)


def test_normalized_solution_schema_allows_type_specific_parameters():
    record = normalized_record()
    record["parts"][0]["parameters"] = {
        "length": 2,
        "source_fields": {"extension": "future-proof"},
    }
    schema_validator().validate(record)


def test_normalized_solution_schema_rejects_non_object_parameters():
    record = normalized_record()
    record["parts"][0]["parameters"] = "{}"
    assert_schema_rejects(record)


def test_normalized_solution_schema_rejects_invalid_rotation():
    record = normalized_record()
    record["parts"][0]["rotation"] = 6
    assert_schema_rejects(record)


def test_normalized_solution_schema_rejects_negative_instruction_cycle():
    record = normalized_record()
    record["programs"][0]["instructions"][0]["cycle"] = -1
    assert_schema_rejects(record)


def test_normalized_solution_schema_rejects_unknown_summary_fields():
    record = normalized_record()
    record["summaries"]["mystery"] = 1
    assert_schema_rejects(record)


def identity_fields() -> dict[str, str]:
    return {
        "solution_id": "om.solution." + "1" * 64,
        "puzzle_id": "om.puzzle.0001",
        "normalizer_version": "normalizer-v1",
    }


def test_normalized_solution_id_is_deterministic():
    normalization = normalization_module()
    fields = identity_fields()
    assert normalization.normalized_solution_id(**fields) == normalization.normalized_solution_id(
        **fields
    )
    value = normalization.normalized_solution_id(**fields)
    assert value.startswith("om.normalized-solution.")
    assert len(value.removeprefix("om.normalized-solution.")) == 64


def test_normalized_solution_id_changes_with_identity_inputs():
    normalization = normalization_module()
    baseline = identity_fields()
    baseline_id = normalization.normalized_solution_id(**baseline)
    replacements = {
        "solution_id": "om.solution." + "2" * 64,
        "puzzle_id": "om.puzzle.0002",
        "normalizer_version": "normalizer-v2",
    }
    for field, replacement in replacements.items():
        changed = dict(baseline)
        changed[field] = replacement
        assert normalization.normalized_solution_id(**changed) != baseline_id


def test_normalized_solution_id_excludes_result_fields_from_interface():
    normalization = normalization_module()
    assert tuple(inspect.signature(normalization.normalized_solution_id).parameters) == (
        "solution_id",
        "puzzle_id",
        "normalizer_version",
    )


def test_solution_normalizer_protocol_is_parser_independent():
    normalization = normalization_module()
    assert getattr(normalization.SolutionNormalizer, "_is_protocol", False)
    assert getattr(normalization.SolutionNormalizer, "_is_runtime_protocol", False)
    assert tuple(inspect.signature(normalization.SolutionNormalizer.normalize).parameters) == (
        "self",
        "value",
    )

    class FakeNormalizer:
        version = "fixture-v1"

        def normalize(self, value: Any) -> dict[str, Any]:
            record = normalized_record()
            record["solution_id"] = value.solution_id
            record["puzzle_id"] = value.puzzle_id
            record["normalizer_version"] = self.version
            record["normalized_solution_id"] = normalization.normalized_solution_id(
                solution_id=value.solution_id,
                puzzle_id=value.puzzle_id,
                normalizer_version=self.version,
            )
            return record

    fake = FakeNormalizer()
    assert isinstance(fake, normalization.SolutionNormalizer)
    value = normalization.SolutionNormalizationInput(
        solution_id="om.solution." + "3" * 64,
        puzzle_id="om.puzzle.0003",
        solution_bytes=b"solution",
    )
    result = fake.normalize(value)
    assert result["solution_id"] == value.solution_id
    assert result["normalizer_version"] == fake.version
