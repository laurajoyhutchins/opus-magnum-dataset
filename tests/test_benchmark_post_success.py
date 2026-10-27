from __future__ import annotations

from dataclasses import replace

import pytest

from opus_corpus import benchmark_results as benchmark


def _identity() -> tuple[benchmark.BenchmarkIdentity, benchmark.BenchmarkRunIdentity]:
    identity = benchmark.BenchmarkIdentity(
        protocol_version="solve-v0.1",
        collection_id="case-a",
        collection_manifest_sha256="1" * 64,
        puzzle_serializer="normalized-puzzle-text",
        puzzle_serializer_version="1",
        candidate_output_compiler="json-base64-solution",
        candidate_output_compiler_version="1",
        verifier_implementation="omsim/libverify",
        verifier_revision="reviewed-a",
        verifier_sha256="2" * 64,
        validation_profile="ordinary-v1",
        attempt_profile="bounded-sequential-v1",
        attempt_budget=2,
        scoring_version="solve-report-v1",
        executable_inventory_sha256="3" * 64,
    )
    run = benchmark.BenchmarkRunIdentity(
        benchmark_id=benchmark.benchmark_id(identity),
        system_id="example-solver",
        system_revision="model-a",
        harness_implementation="opus-corpus",
        harness_revision="rev-a",
        generation_config_sha256="4" * 64,
    )
    return identity, run


def _attempt(
    identity: benchmark.BenchmarkIdentity,
    run: benchmark.BenchmarkRunIdentity,
    index: int,
    outcome: str,
) -> dict:
    success = outcome == "success"
    return benchmark.build_attempt_result(
        benchmark_id=benchmark.benchmark_id(identity),
        run_id=benchmark.benchmark_run_id(run),
        puzzle_id="puzzle-a",
        attempt_index=index,
        outcome=outcome,
        candidate_sha256="5" * 64,
        verification_id="om.verification." + "6" * 64,
        cost=7 if success else None,
        cycles=8 if success else None,
        area=9 if success else None,
        instructions=10 if success else None,
        error_code=None if success else "sim_error",
        model_calls=1,
        input_tokens=20,
        output_tokens=10,
        verifier_calls=1,
    )


@pytest.mark.parametrize("outcomes", [
    ("success", "simulation_failed"),
    ("success", "success"),
])
def test_puzzle_result_rejects_attempt_after_first_success(outcomes: tuple[str, str]) -> None:
    identity, run = _identity()
    attempts = [
        _attempt(identity, run, index, outcome)
        for index, outcome in enumerate(outcomes, start=1)
    ]
    with pytest.raises(benchmark.BenchmarkResultError, match="after its first successful"):
        benchmark.build_puzzle_result(
            benchmark_id=benchmark.benchmark_id(identity),
            run_id=benchmark.benchmark_run_id(run),
            puzzle_id="puzzle-a",
            attempts=attempts,
        )


@pytest.mark.parametrize("outcomes", [
    ("success", "simulation_failed"),
    ("success", "success"),
])
def test_aggregate_rejects_source_shaped_forged_post_success_attempts(
    outcomes: tuple[str, str],
) -> None:
    identity, run = _identity()
    valid_first = benchmark.build_puzzle_result(
        benchmark_id=benchmark.benchmark_id(identity),
        run_id=benchmark.benchmark_run_id(run),
        puzzle_id="puzzle-a",
        attempts=[_attempt(identity, run, 1, "success")],
    )
    # The report validator must enforce the same invariant on imported data,
    # even if the puzzle_result builder was not used by the record producer.
    forged = dict(valid_first)
    forged["attempts"] = [
        _attempt(identity, run, index, outcome)
        for index, outcome in enumerate(outcomes, start=1)
    ]
    with pytest.raises(benchmark.BenchmarkResultError, match="after its first successful"):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=["puzzle-a"],
            puzzle_results=[forged],
        )


def test_failed_then_successful_attempt_is_valid_and_counts_only_actual_work() -> None:
    identity, run = _identity()
    puzzle = benchmark.build_puzzle_result(
        benchmark_id=benchmark.benchmark_id(identity),
        run_id=benchmark.benchmark_run_id(run),
        puzzle_id="puzzle-a",
        attempts=[
            _attempt(identity, run, 2, "success"),
            _attempt(identity, run, 1, "simulation_failed"),
        ],
    )
    assert puzzle["first_success_attempt"] == 2
    report = benchmark.aggregate_benchmark_report(
        identity=identity,
        run=run,
        expected_puzzle_ids=["puzzle-a"],
        puzzle_results=[puzzle],
    )
    assert report["attempt_count"] == 2
    assert report["model_calls"] == 2
    assert report["verifier_calls"] == 2
    assert report["solved_count"] == 1
    assert report["outcome_counts"]["simulation_failed"] == 1
    assert report["outcome_counts"]["success"] == 1
