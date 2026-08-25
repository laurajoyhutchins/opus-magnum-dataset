from __future__ import annotations

import importlib
from dataclasses import replace
from typing import Any

import pytest

from opus_corpus.hashing import canonical_json_bytes
from opus_corpus.schema_resources import load_schema_resource


def benchmark_module() -> Any:
    return importlib.import_module("opus_corpus.benchmark_results")


def schema_validator() -> Any:
    jsonschema = importlib.import_module("jsonschema")
    schema = load_schema_resource("benchmark-results.schema.json").schema
    return jsonschema.Draft202012Validator(schema)


def benchmark_identity() -> Any:
    benchmark = benchmark_module()
    return benchmark.BenchmarkIdentity(
        protocol_version="solve-v0.1",
        collection_id="base-game-2026-06-16",
        collection_manifest_sha256="1" * 64,
        puzzle_serializer="normalized-puzzle-text",
        puzzle_serializer_version="1",
        candidate_output_compiler="json-base64-solution",
        candidate_output_compiler_version="1",
        verifier_implementation="omsim/libverify",
        verifier_revision="rev-a",
        verifier_sha256="2" * 64,
        validation_profile="ordinary-v1",
        attempt_profile="one-shot",
        attempt_budget=1,
        scoring_version="solve-report-v1",
    )


def run_identity() -> Any:
    benchmark = benchmark_module()
    return benchmark.BenchmarkRunIdentity(
        benchmark_id=benchmark.benchmark_id(benchmark_identity()),
        system_id="example-solver",
        system_revision="model-rev-a",
        harness_implementation="opus-corpus",
        harness_revision="git-rev-a",
        generation_config_sha256="3" * 64,
    )


def success_attempt(*, puzzle_id: str = "puzzle-a", attempt_index: int = 1) -> dict[str, object]:
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    return benchmark.build_attempt_result(
        benchmark_id=benchmark.benchmark_id(identity),
        run_id=benchmark.benchmark_run_id(run),
        puzzle_id=puzzle_id,
        attempt_index=attempt_index,
        outcome="success",
        candidate_sha256="4" * 64,
        verification_id="om.verification." + "5" * 64,
        cost=42,
        cycles=17,
        area=13,
        instructions=9,
        error_code=None,
        model_calls=1,
        input_tokens=100,
        output_tokens=40,
        verifier_calls=1,
    )


def failure_attempt(
    *,
    puzzle_id: str = "puzzle-b",
    attempt_index: int = 1,
    outcome: str = "simulation_failed",
    model_calls: int | None = 1,
    input_tokens: int | None = 80,
    output_tokens: int | None = 25,
) -> dict[str, object]:
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    return benchmark.build_attempt_result(
        benchmark_id=benchmark.benchmark_id(identity),
        run_id=benchmark.benchmark_run_id(run),
        puzzle_id=puzzle_id,
        attempt_index=attempt_index,
        outcome=outcome,
        candidate_sha256="6" * 64,
        verification_id="om.verification." + "7" * 64,
        cost=None,
        cycles=None,
        area=None,
        instructions=None,
        error_code="sim_error",
        model_calls=model_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        verifier_calls=1,
    )


def test_benchmark_id_is_deterministic_and_commits_to_every_identity_field():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    value = benchmark.benchmark_id(identity)
    assert value == benchmark.benchmark_id(identity)
    assert value.startswith("om.benchmark.")

    replacements = {
        "protocol_version": "solve-v0.2",
        "collection_id": "held-out-v1",
        "collection_manifest_sha256": "8" * 64,
        "puzzle_serializer": "raw-puzzle",
        "puzzle_serializer_version": "2",
        "candidate_output_compiler": "structured-solution",
        "candidate_output_compiler_version": "2",
        "verifier_implementation": "other-verifier",
        "verifier_revision": "rev-b",
        "verifier_sha256": "9" * 64,
        "validation_profile": "record-v1",
        "attempt_profile": "interactive-3",
        "attempt_budget": 3,
        "scoring_version": "solve-report-v2",
    }
    for field, replacement in replacements.items():
        assert benchmark.benchmark_id(replace(identity, **{field: replacement})) != value


def test_benchmark_run_id_commits_to_system_harness_and_generation_config():
    benchmark = benchmark_module()
    run = run_identity()
    value = benchmark.benchmark_run_id(run)
    assert value == benchmark.benchmark_run_id(run)
    assert value.startswith("om.benchmark-run.")

    replacements = {
        "benchmark_id": "om.benchmark." + "a" * 64,
        "system_id": "other-solver",
        "system_revision": "model-rev-b",
        "harness_implementation": "other-harness",
        "harness_revision": "git-rev-b",
        "generation_config_sha256": "b" * 64,
    }
    for field, replacement in replacements.items():
        assert benchmark.benchmark_run_id(replace(run, **{field: replacement})) != value


def test_schema_accepts_identity_attempt_puzzle_and_aggregate_records():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    attempt = success_attempt()
    puzzle = benchmark.build_puzzle_result(
        benchmark_id=benchmark.benchmark_id(identity),
        run_id=benchmark.benchmark_run_id(run),
        puzzle_id="puzzle-a",
        attempts=[attempt],
    )
    report = benchmark.aggregate_benchmark_report(
        identity=identity,
        run=run,
        expected_puzzle_ids=["puzzle-a"],
        puzzle_results=[puzzle],
    )

    validator = schema_validator()
    for record in (
        benchmark.benchmark_identity_record(identity),
        benchmark.benchmark_run_identity_record(run),
        attempt,
        puzzle,
        report,
    ):
        validator.validate(record)


def test_schema_rejects_unknown_fields():
    jsonschema = importlib.import_module("jsonschema")
    record = success_attempt()
    record["source_claimed_score"] = 12
    with pytest.raises(jsonschema.ValidationError):
        schema_validator().validate(record)


def test_attempt_builder_enforces_success_and_failure_payload_invariants():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    common = {
        "benchmark_id": benchmark.benchmark_id(identity),
        "run_id": benchmark.benchmark_run_id(run),
        "puzzle_id": "puzzle-a",
        "attempt_index": 1,
        "candidate_sha256": "c" * 64,
        "model_calls": 1,
        "input_tokens": 10,
        "output_tokens": 5,
        "verifier_calls": 1,
    }

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_attempt_result(
            **common,
            outcome="success",
            verification_id=None,
            cost=1,
            cycles=2,
            area=3,
            instructions=4,
            error_code=None,
        )

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_attempt_result(
            **common,
            outcome="simulation_failed",
            verification_id=None,
            cost=1,
            cycles=None,
            area=None,
            instructions=None,
            error_code="sim_error",
        )


def test_puzzle_result_sorts_attempts_and_derives_first_success():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    first = failure_attempt(puzzle_id="puzzle-a", attempt_index=1)
    second = success_attempt(puzzle_id="puzzle-a", attempt_index=2)

    result = benchmark.build_puzzle_result(
        benchmark_id=benchmark.benchmark_id(identity),
        run_id=benchmark.benchmark_run_id(run),
        puzzle_id="puzzle-a",
        attempts=[second, first],
    )

    assert [attempt["attempt_index"] for attempt in result["attempts"]] == [1, 2]
    assert result["solved"] is True
    assert result["first_success_attempt"] == 2


def test_puzzle_result_rejects_duplicate_gapped_or_mismatched_attempts():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    kwargs = {
        "benchmark_id": benchmark.benchmark_id(identity),
        "run_id": benchmark.benchmark_run_id(run),
        "puzzle_id": "puzzle-a",
    }
    first = failure_attempt(puzzle_id="puzzle-a", attempt_index=1)

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_puzzle_result(**kwargs, attempts=[first, dict(first)])

    third = success_attempt(puzzle_id="puzzle-a", attempt_index=3)
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_puzzle_result(**kwargs, attempts=[first, third])

    mismatched = dict(first)
    mismatched["puzzle_id"] = "puzzle-b"
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_puzzle_result(**kwargs, attempts=[mismatched])


def test_aggregate_is_deterministic_and_counts_outcomes_and_resources():
    benchmark = benchmark_module()
    identity = replace(benchmark_identity(), attempt_profile="interactive-2", attempt_budget=2)
    run = replace(run_identity(), benchmark_id=benchmark.benchmark_id(identity))
    run_id = benchmark.benchmark_run_id(run)
    benchmark_id = benchmark.benchmark_id(identity)

    puzzle_a = benchmark.build_puzzle_result(
        benchmark_id=benchmark_id,
        run_id=run_id,
        puzzle_id="puzzle-a",
        attempts=[
            benchmark.build_attempt_result(
                benchmark_id=benchmark_id,
                run_id=run_id,
                puzzle_id="puzzle-a",
                attempt_index=1,
                outcome="solution_parse_failed",
                candidate_sha256="d" * 64,
                verification_id="om.verification." + "e" * 64,
                cost=None,
                cycles=None,
                area=None,
                instructions=None,
                error_code="parse_error",
                model_calls=1,
                input_tokens=30,
                output_tokens=10,
                verifier_calls=1,
            ),
            benchmark.build_attempt_result(
                benchmark_id=benchmark_id,
                run_id=run_id,
                puzzle_id="puzzle-a",
                attempt_index=2,
                outcome="success",
                candidate_sha256="f" * 64,
                verification_id="om.verification." + "1" * 64,
                cost=5,
                cycles=6,
                area=7,
                instructions=8,
                error_code=None,
                model_calls=1,
                input_tokens=40,
                output_tokens=20,
                verifier_calls=1,
            ),
        ],
    )
    puzzle_b = benchmark.build_puzzle_result(
        benchmark_id=benchmark_id,
        run_id=run_id,
        puzzle_id="puzzle-b",
        attempts=[
            benchmark.build_attempt_result(
                benchmark_id=benchmark_id,
                run_id=run_id,
                puzzle_id="puzzle-b",
                attempt_index=1,
                outcome="output_compile_failed",
                candidate_sha256="2" * 64,
                verification_id=None,
                cost=None,
                cycles=None,
                area=None,
                instructions=None,
                error_code="compile_error",
                model_calls=1,
                input_tokens=25,
                output_tokens=5,
                verifier_calls=0,
            )
        ],
    )

    report_a = benchmark.aggregate_benchmark_report(
        identity=identity,
        run=run,
        expected_puzzle_ids=["puzzle-b", "puzzle-a"],
        puzzle_results=[puzzle_b, puzzle_a],
    )
    report_b = benchmark.aggregate_benchmark_report(
        identity=identity,
        run=run,
        expected_puzzle_ids=["puzzle-a", "puzzle-b"],
        puzzle_results=[puzzle_a, puzzle_b],
    )

    assert canonical_json_bytes(report_a) == canonical_json_bytes(report_b)
    assert report_a["puzzle_count"] == 2
    assert report_a["solved_count"] == 1
    assert report_a["unsolved_count"] == 1
    assert report_a["solve_rate_numerator"] == 1
    assert report_a["solve_rate_denominator"] == 2
    assert report_a["attempt_count"] == 3
    assert report_a["outcome_counts"] == {
        "output_compile_failed": 1,
        "solution_parse_failed": 1,
        "puzzle_solution_mismatch": 0,
        "simulation_failed": 0,
        "success": 1,
    }
    assert report_a["verifier_calls"] == 2
    assert report_a["model_calls"] == 3
    assert report_a["input_tokens"] == 95
    assert report_a["output_tokens"] == 35


def test_aggregate_rejects_duplicate_puzzles_mismatched_run_and_attempt_budget_overflow():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    benchmark_id = benchmark.benchmark_id(identity)
    run_id = benchmark.benchmark_run_id(run)
    puzzle = benchmark.build_puzzle_result(
        benchmark_id=benchmark_id,
        run_id=run_id,
        puzzle_id="puzzle-a",
        attempts=[success_attempt()],
    )

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=["puzzle-a"],
            puzzle_results=[puzzle, dict(puzzle)],
        )

    wrong_run = dict(puzzle)
    wrong_run["run_id"] = "om.benchmark-run." + "0" * 64
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=["puzzle-a"],
            puzzle_results=[wrong_run],
        )

    over_budget = dict(puzzle)
    over_budget["attempts"] = [success_attempt(attempt_index=2)]
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=["puzzle-a"],
            puzzle_results=[over_budget],
        )


def test_aggregate_resource_totals_are_null_when_any_observation_is_missing():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    benchmark_id = benchmark.benchmark_id(identity)
    run_id = benchmark.benchmark_run_id(run)
    puzzle = benchmark.build_puzzle_result(
        benchmark_id=benchmark_id,
        run_id=run_id,
        puzzle_id="puzzle-b",
        attempts=[
            benchmark.build_attempt_result(
                benchmark_id=benchmark_id,
                run_id=run_id,
                puzzle_id="puzzle-b",
                attempt_index=1,
                outcome="simulation_failed",
                candidate_sha256="6" * 64,
                verification_id="om.verification." + "7" * 64,
                cost=None,
                cycles=None,
                area=None,
                instructions=None,
                error_code="sim_error",
                model_calls=None,
                input_tokens=None,
                output_tokens=None,
                verifier_calls=1,
            )
        ],
    )

    report = benchmark.aggregate_benchmark_report(
        identity=identity,
        run=run,
        expected_puzzle_ids=["puzzle-b"],
        puzzle_results=[puzzle],
    )
    assert report["model_calls"] is None
    assert report["input_tokens"] is None
    assert report["output_tokens"] is None
    assert report["verifier_calls"] == 1


def test_attempt_verifier_lineage_invariants_fail_closed_in_builder_and_schema():
    benchmark = benchmark_module()
    identity = benchmark_identity()
    run = run_identity()
    common = {
        "benchmark_id": benchmark.benchmark_id(identity),
        "run_id": benchmark.benchmark_run_id(run),
        "puzzle_id": "puzzle-a",
        "attempt_index": 1,
        "candidate_sha256": "4" * 64,
        "model_calls": 1,
        "input_tokens": 10,
        "output_tokens": 5,
    }

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_attempt_result(
            **common,
            outcome="success",
            verification_id="om.verification." + "5" * 64,
            cost=1,
            cycles=2,
            area=3,
            instructions=4,
            error_code=None,
            verifier_calls=0,
        )

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.build_attempt_result(
            **common,
            outcome="output_compile_failed",
            verification_id="om.verification." + "5" * 64,
            cost=None,
            cycles=None,
            area=None,
            instructions=None,
            error_code="compile_error",
            verifier_calls=1,
        )

    jsonschema = importlib.import_module("jsonschema")
    success_record = success_attempt()
    success_record["verifier_calls"] = 0
    with pytest.raises(jsonschema.ValidationError):
        schema_validator().validate(success_record)

    compile_failure_record = success_attempt()
    compile_failure_record.update(
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
    with pytest.raises(jsonschema.ValidationError):
        schema_validator().validate(compile_failure_record)
