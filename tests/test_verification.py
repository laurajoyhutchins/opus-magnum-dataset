from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path("schemas/verification.schema.json")


def jsonschema_module() -> Any:
    return importlib.import_module("jsonschema")


def verification_module() -> Any:
    return importlib.import_module("opus_corpus.verification")


def schema_validator() -> Any:
    jsonschema = jsonschema_module()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def successful_record() -> dict[str, object]:
    return {
        "verification_id": "om.verification." + "a" * 64,
        "puzzle_artifact_id": "om.puzzle-artifact." + "b" * 64,
        "solution_id": "om.solution." + "c" * 64,
        "verifier_implementation": "omsim",
        "verifier_revision": "0123456789abcdef",
        "verifier_sha256": "d" * 64,
        "validation_profile": "ordinary-v1",
        "parse_status": "passed",
        "simulation_status": "passed",
        "cost": 42,
        "cycles": 17,
        "area": 13,
        "instructions": 9,
        "vanilla_constructible": True,
        "record_eligible": True,
        "error_code": None,
        "error_detail": None,
    }


def assert_schema_rejects(record: dict[str, object]) -> None:
    validation_error = jsonschema_module().ValidationError
    try:
        schema_validator().validate(record)
    except validation_error:
        return
    raise AssertionError("verification schema unexpectedly accepted invalid record")


def test_verification_schema_accepts_successful_record():
    schema_validator().validate(successful_record())


def test_verification_schema_accepts_failed_parse_with_null_metrics():
    record = successful_record()
    record.update(
        {
            "parse_status": "failed",
            "simulation_status": "not_run",
            "cost": None,
            "cycles": None,
            "area": None,
            "instructions": None,
            "vanilla_constructible": None,
            "record_eligible": None,
            "error_code": "solution_parse_failed",
            "error_detail": "invalid instruction stream",
        }
    )
    schema_validator().validate(record)


def test_verification_schema_rejects_unknown_fields():
    record = successful_record()
    record["source_claimed_cycles"] = 17
    assert_schema_rejects(record)


def test_verification_schema_rejects_invalid_status():
    record = successful_record()
    record["simulation_status"] = "unknown"
    assert_schema_rejects(record)


def identity_fields() -> dict[str, str | None]:
    return {
        "puzzle_artifact_id": "om.puzzle-artifact." + "1" * 64,
        "solution_id": "om.solution." + "2" * 64,
        "verifier_implementation": "omsim",
        "verifier_revision": "rev-a",
        "verifier_sha256": "3" * 64,
        "validation_profile": "ordinary-v1",
    }


def test_verification_id_is_deterministic():
    verification = verification_module()
    fields = identity_fields()
    assert verification.verification_id(**fields) == verification.verification_id(**fields)
    value = verification.verification_id(**fields)
    assert value.startswith("om.verification.")
    assert len(value.removeprefix("om.verification.")) == 64


def test_verification_id_changes_when_evaluation_identity_changes():
    verification = verification_module()
    replacements = {
        "puzzle_artifact_id": "om.puzzle-artifact." + "4" * 64,
        "solution_id": "om.solution." + "5" * 64,
        "verifier_implementation": "libverify",
        "verifier_revision": "rev-b",
        "verifier_sha256": "6" * 64,
        "validation_profile": "record-v1",
    }
    baseline = identity_fields()
    baseline_id = verification.verification_id(**baseline)
    for field, replacement in replacements.items():
        changed = dict(baseline)
        changed[field] = replacement
        assert verification.verification_id(**changed) != baseline_id


def test_verification_id_excludes_result_fields_from_its_interface():
    verification = verification_module()
    assert tuple(inspect.signature(verification.verification_id).parameters) == (
        "puzzle_artifact_id",
        "solution_id",
        "verifier_implementation",
        "verifier_revision",
        "verifier_sha256",
        "validation_profile",
    )


def test_verifier_protocol_is_simulator_independent():
    verification = verification_module()

    class FakeVerifier:
        def verify(self, value: Any) -> Any:
            identity = {
                "puzzle_artifact_id": value.puzzle_artifact_id,
                "solution_id": value.solution_id,
                "verifier_implementation": "fake",
                "verifier_revision": "fixture-v1",
                "verifier_sha256": None,
                "validation_profile": value.validation_profile,
            }
            return verification.VerificationResult(
                verification_id=verification.verification_id(**identity),
                puzzle_artifact_id=value.puzzle_artifact_id,
                solution_id=value.solution_id,
                verifier_implementation="fake",
                verifier_revision="fixture-v1",
                verifier_sha256=None,
                validation_profile=value.validation_profile,
                parse_status="passed",
                simulation_status="passed",
                cost=1,
                cycles=2,
                area=3,
                instructions=4,
                vanilla_constructible=True,
                record_eligible=True,
                error_code=None,
                error_detail=None,
            )

    def run(verifier: Any, value: Any) -> Any:
        return verifier.verify(value)

    value = verification.VerificationInput(
        puzzle_artifact_id="om.puzzle-artifact." + "7" * 64,
        solution_id="om.solution." + "8" * 64,
        puzzle_bytes=b"puzzle",
        solution_bytes=b"solution",
        validation_profile="ordinary-v1",
    )
    result = run(FakeVerifier(), value)
    assert result.simulation_status == "passed"
    assert result.cost == 1
