from __future__ import annotations

import pytest

from opus_corpus import benchmark_results as benchmark


def identities() -> tuple[benchmark.BenchmarkIdentity, benchmark.BenchmarkRunIdentity]:
    identity = benchmark.BenchmarkIdentity(
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
    run = benchmark.BenchmarkRunIdentity(
        benchmark_id=benchmark.benchmark_id(identity),
        system_id="example-solver",
        system_revision="model-rev-a",
        harness_implementation="opus-corpus",
        harness_revision="git-rev-a",
        generation_config_sha256="3" * 64,
    )
    return identity, run


def puzzle_result(puzzle_id: str) -> dict[str, object]:
    identity, run = identities()
    benchmark_id = benchmark.benchmark_id(identity)
    run_id = benchmark.benchmark_run_id(run)
    attempt = benchmark.build_attempt_result(
        benchmark_id=benchmark_id,
        run_id=run_id,
        puzzle_id=puzzle_id,
        attempt_index=1,
        outcome="output_compile_failed",
        candidate_sha256="4" * 64,
        verification_id=None,
        cost=None,
        cycles=None,
        area=None,
        instructions=None,
        error_code="compile_error",
        model_calls=1,
        input_tokens=10,
        output_tokens=5,
        verifier_calls=0,
    )
    return benchmark.build_puzzle_result(
        benchmark_id=benchmark_id,
        run_id=run_id,
        puzzle_id=puzzle_id,
        attempts=[attempt],
    )


def test_aggregate_rejects_partial_collection_coverage():
    identity, run = identities()
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=["puzzle-a", "puzzle-b"],
            puzzle_results=[puzzle_result("puzzle-a")],
        )


def test_aggregate_rejects_unexpected_puzzle_ids():
    identity, run = identities()
    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=["puzzle-a"],
            puzzle_results=[puzzle_result("puzzle-b")],
        )


def test_aggregate_rejects_empty_or_duplicate_expected_puzzle_ids():
    identity, run = identities()
    puzzle = puzzle_result("puzzle-a")

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=[],
            puzzle_results=[puzzle],
        )

    with pytest.raises(benchmark.BenchmarkResultError):
        benchmark.aggregate_benchmark_report(
            identity=identity,
            run=run,
            expected_puzzle_ids=["puzzle-a", "puzzle-a"],
            puzzle_results=[puzzle],
        )


def test_aggregate_accepts_complete_collection_independent_of_input_order():
    identity, run = identities()
    report = benchmark.aggregate_benchmark_report(
        identity=identity,
        run=run,
        expected_puzzle_ids=["puzzle-b", "puzzle-a"],
        puzzle_results=[puzzle_result("puzzle-a"), puzzle_result("puzzle-b")],
    )
    assert report["puzzle_count"] == 2
    assert report["solve_rate_denominator"] == 2
