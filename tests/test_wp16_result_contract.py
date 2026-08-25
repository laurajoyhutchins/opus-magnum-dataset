from __future__ import annotations

import importlib
from dataclasses import fields, replace
from typing import Any

import pytest


BENCHMARK_ID = "om.benchmark." + "1" * 64
RUN_ID = "om.benchmark-run." + "2" * 64
CANDIDATE_SHA256 = "3" * 64
VERIFICATION_ID = "om.verification." + "4" * 64


def benchmark_module() -> Any:
    return importlib.import_module("opus_corpus.benchmark_results")


def attempt(**overrides: object) -> dict[str, object]:
    benchmark = benchmark_module()
    values: dict[str, object] = {
        "benchmark_id": BENCHMARK_ID,
        "run_id": RUN_ID,
        "puzzle_id": "puzzle-a",
        "attempt_index": 1,
        "outcome": "simulation_failed",
        "candidate_sha256": CANDIDATE_SHA256,
        "verification_id": VERIFICATION_ID,
        "cost": None,
        "cycles": None,
        "area": None,
        "instructions": None,
        "error_code": "simulation_failed",
        "model_calls": 1,
        "input_tokens": 10,
        "output_tokens": 5,
        "verifier_calls": 1,
    }
    values.update(overrides)
    return benchmark.build_attempt_result(**values)


def test_benchmark_identity_commits_to_executable_inventory_hash() -> None:
    benchmark = benchmark_module()
    field_names = {field.name for field in fields(benchmark.BenchmarkIdentity)}
    assert "executable_inventory_sha256" in field_names

    identity = benchmark.BenchmarkIdentity(
        protocol_version="solve-v0.1",
        collection_id="collection-a",
        collection_manifest_sha256="5" * 64,
        puzzle_serializer="opus-magnum-puzzle-text",
        puzzle_serializer_version="2",
        candidate_output_compiler="json-base64-solution",
        candidate_output_compiler_version="1",
        verifier_implementation="omsim-libverify",
        verifier_revision="verifier-rev",
        verifier_sha256="6" * 64,
        validation_profile="omsim-libverify-v1",
        attempt_profile="one-shot",
        attempt_budget=1,
        scoring_version="solve-report-v1",
        executable_inventory_sha256="7" * 64,
    )
    changed = replace(identity, executable_inventory_sha256="8" * 64)
    assert benchmark.benchmark_id(identity) != benchmark.benchmark_id(changed)


def test_compile_failure_has_no_candidate_or_verifier_lineage() -> None:
    record = attempt(
        outcome="output_compile_failed",
        candidate_sha256=None,
        verification_id=None,
        error_code="not_json",
        verifier_calls=0,
    )
    assert record["candidate_sha256"] is None
    assert record["verification_id"] is None
    assert record["verifier_calls"] == 0


def test_compile_failure_rejects_a_fake_candidate_hash() -> None:
    benchmark = benchmark_module()
    with pytest.raises(benchmark.BenchmarkResultError):
        attempt(
            outcome="output_compile_failed",
            verification_id=None,
            error_code="not_json",
            verifier_calls=0,
        )


@pytest.mark.parametrize("outcome", ["solution_parse_failed", "puzzle_solution_mismatch"])
def test_pre_verifier_failures_preserve_candidate_without_fake_verifier_lineage(
    outcome: str,
) -> None:
    record = attempt(
        outcome=outcome,
        verification_id=None,
        error_code=outcome,
        verifier_calls=0,
    )
    assert record["candidate_sha256"] == CANDIDATE_SHA256
    assert record["verification_id"] is None
    assert record["verifier_calls"] == 0


def test_post_verifier_failure_still_requires_verifier_lineage() -> None:
    benchmark = benchmark_module()
    with pytest.raises(benchmark.BenchmarkResultError):
        attempt(
            outcome="simulation_failed",
            verification_id=None,
            verifier_calls=0,
        )