from __future__ import annotations

import base64
import importlib
import json
import struct
from dataclasses import replace

import pytest

from opus_corpus.hashing import sha256_bytes
from opus_corpus.solution_parser import SolutionParseError


def _solution_bytes(puzzle_name: str = "P001") -> bytes:
    puzzle = puzzle_name.encode("utf-8")
    solution = b"fixture"
    assert len(puzzle) < 0x80
    assert len(solution) < 0x80
    return (
        struct.pack("<I", 7)
        + bytes([len(puzzle)])
        + puzzle
        + bytes([len(solution)])
        + solution
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
    )


def _raw_output(payload: bytes) -> str:
    return json.dumps(
        {
            "format": "om-solution-base64-v1",
            "solution_base64": base64.b64encode(payload).decode("ascii"),
        },
        separators=(",", ":"),
    )


def _candidate_module():
    return importlib.import_module("opus_corpus.benchmark_candidate")


def test_candidate_output_compiler_identity_is_explicit_and_versioned() -> None:
    candidate = _candidate_module()

    assert candidate.CANDIDATE_OUTPUT_COMPILER == "json-base64-solution"
    assert candidate.CANDIDATE_OUTPUT_COMPILER_VERSION == "1"
    assert candidate.CANDIDATE_OUTPUT_FORMAT == "om-solution-base64-v1"


def test_compile_candidate_output_returns_exact_bytes_and_content_hash() -> None:
    candidate = _candidate_module()
    payload = _solution_bytes()

    compiled = candidate.compile_candidate_output(_raw_output(payload))

    assert compiled.solution_bytes == payload
    assert compiled.candidate_sha256 == sha256_bytes(payload)


def test_compile_candidate_output_accepts_only_one_strict_json_envelope() -> None:
    candidate = _candidate_module()
    payload = _solution_bytes()
    canonical = _raw_output(payload)

    assert candidate.compile_candidate_output(f" \n{canonical}\t").solution_bytes == payload

    failures = [
        (f"```json\n{canonical}\n```", "not_json"),
        (f"candidate: {canonical}", "not_json"),
        (f"{canonical}\n{canonical}", "trailing_material"),
        (
            '{"format":"om-solution-base64-v1","format":"om-solution-base64-v1",'
            '"solution_base64":"AA=="}',
            "duplicate_field",
        ),
        (
            json.dumps(
                {
                    "format": "om-solution-base64-v1",
                    "solution_base64": "AA==",
                    "comment": "extra",
                }
            ),
            "invalid_envelope",
        ),
        (json.dumps({"format": "om-solution-base64-v1"}), "invalid_envelope"),
        (
            json.dumps({"format": "raw", "solution_base64": "AA=="}),
            "unsupported_format",
        ),
        (
            json.dumps(
                {"format": "om-solution-base64-v1", "solution_base64": "!!!!"}
            ),
            "invalid_base64",
        ),
        (
            json.dumps(
                {"format": "om-solution-base64-v1", "solution_base64": "TQ===="}
            ),
            "noncanonical_base64",
        ),
        (
            json.dumps(
                {"format": "om-solution-base64-v1", "solution_base64": ""}
            ),
            "empty_candidate",
        ),
    ]

    for raw_output, code in failures:
        with pytest.raises(candidate.CandidateOutputCompileError) as exc:
            candidate.compile_candidate_output(raw_output)
        assert exc.value.code == code


def test_solution_parse_failure_remains_distinct_from_output_compilation_failure() -> None:
    candidate = _candidate_module()
    compiled = candidate.compile_candidate_output(_raw_output(b"not-a-solution"))

    with pytest.raises(SolutionParseError):
        candidate.parse_candidate_solution(compiled, expected_puzzle_name="P001")


def test_solution_puzzle_binding_mismatch_has_a_stable_typed_error() -> None:
    candidate = _candidate_module()
    compiled = candidate.compile_candidate_output(_raw_output(_solution_bytes("P001")))

    with pytest.raises(candidate.PuzzleSolutionMismatchError) as exc:
        candidate.parse_candidate_solution(compiled, expected_puzzle_name="P002")

    assert exc.value.code == "puzzle_solution_mismatch"
    assert exc.value.expected_puzzle_name == "P002"
    assert exc.value.observed_puzzle_name == "P001"


def test_benchmark_identity_names_and_commits_to_candidate_output_compiler() -> None:
    benchmark = importlib.import_module("opus_corpus.benchmark_results")
    identity = benchmark.BenchmarkIdentity(
        protocol_version="solve-v0.1",
        collection_id="base-game-2026-06-16",
        collection_manifest_sha256="1" * 64,
        puzzle_serializer="puzzle-definition-text",
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
        executable_inventory_sha256="6" * 64,
    )

    record = benchmark.benchmark_identity_record(identity)
    assert record["candidate_output_compiler"] == "json-base64-solution"
    assert record["candidate_output_compiler_version"] == "1"
    assert "output_parser" not in record
    assert benchmark.benchmark_id(
        replace(identity, candidate_output_compiler_version="2")
    ) != benchmark.benchmark_id(identity)