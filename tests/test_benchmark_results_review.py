from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator, ValidationError

from opus_corpus import benchmark_results as benchmark
from opus_corpus.schema_resources import load_schema_resource


def identities() -> tuple[str, str]:
    identity = benchmark.BenchmarkIdentity(
        protocol_version="solve-v0.1",
        collection_id="base-game-2026-06-16",
        collection_manifest_sha256="1" * 64,
        puzzle_serializer="normalized-puzzle-text",
        puzzle_serializer_version="1",
        output_parser="exact-solution-bytes",
        output_parser_version="1",
        verifier_implementation="omsim/libverify",
        verifier_revision="rev-a",
        verifier_sha256="2" * 64,
        validation_profile="ordinary-v1",
        attempt_profile="one-shot",
        attempt_budget=1,
        scoring_version="solve-report-v1",
    )
    benchmark_id = benchmark.benchmark_id(identity)
    run = benchmark.BenchmarkRunIdentity(
        benchmark_id=benchmark_id,
        system_id="example-solver",
        system_revision="model-rev-a",
        harness_implementation="opus-corpus",
        harness_revision="git-rev-a",
        generation_config_sha256="3" * 64,
    )
    return benchmark_id, benchmark.benchmark_run_id(run)


def attempt_fields() -> dict[str, object]:
    benchmark_id, run_id = identities()
    return {
        "benchmark_id": benchmark_id,
        "run_id": run_id,
        "puzzle_id": "puzzle-a",
        "attempt_index": 1,
        "candidate_sha256": "4" * 64,
        "model_calls": 1,
        "input_tokens": 10,
        "output_tokens": 5,
    }


def schema_validator() -> Draft202012Validator:
    schema = load_schema_resource("benchmark-results.schema.json").schema
    return Draft202012Validator(schema)


def valid_success() -> dict[str, object]:
    return benchmark.build_attempt_result(
        **attempt_fields(),
        outcome="success",
        verification_id="om.verification." + "5" * 64,
        cost=1,
        cycles=2,
        area=3,
        instructions=4,
        error_code=None,
        verifier_calls=1,
    )


def test_success_requires_at_least_one_verifier_call():
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_attempt_result(
            **attempt_fields(),
            outcome="success",
            verification_id="om.verification." + "5" * 64,
            cost=1,
            cycles=2,
            area=3,
            instructions=4,
            error_code=None,
            verifier_calls=0,
        )


def test_output_compile_failure_cannot_claim_verifier_lineage_or_calls():
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_attempt_result(
            **attempt_fields(),
            outcome="output_compile_failed",
            verification_id="om.verification." + "5" * 64,
            cost=None,
            cycles=None,
            area=None,
            instructions=None,
            error_code="compile_error",
            verifier_calls=1,
        )


def test_schema_rejects_success_without_a_verifier_call():
    record = valid_success()
    record["verifier_calls"] = 0
    with pytest.raises(ValidationError):
        schema_validator().validate(record)


def test_schema_rejects_compile_failure_with_verifier_lineage():
    record = valid_success()
    record.update(
        {
            "outcome": "output_compile_failed",
            "verification_id": "om.verification." + "6" * 64,
            "cost": None,
            "cycles": None,
            "area": None,
            "instructions": None,
            "error_code": "compile_error",
            "verifier_calls": 1,
        }
    )
    with pytest.raises(ValidationError):
        schema_validator().validate(record)
