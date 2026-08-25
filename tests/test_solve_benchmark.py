from __future__ import annotations

import base64
import importlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

from opus_corpus.benchmark_eligibility import derive_benchmark_eligibility
from opus_corpus.collections import CollectionDefinition
from opus_corpus.hashing import canonical_json_bytes, sha256_bytes
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.puzzle_definition import build_puzzle_definition
from opus_corpus.verification import VerificationInput, VerificationResult, verification_id


def solve_module() -> Any:
    return importlib.import_module("opus_corpus.solve_benchmark")


def collection(count: int = 6) -> CollectionDefinition:
    rows = tuple(
        {
            "puzzle_id": f"om.puzzle.{index:04d}",
            "display_name": f"Puzzle {index}",
            "kind": "campaign",
            "group": "fixture",
            "game_puzzle_id": f"P{index:03d}",
            "leaderboard_key": f"PUZZLE_{index}",
            "puzzle_type": "normal",
        }
        for index in range(1, count + 1)
    )
    return CollectionDefinition(
        collection_id="fixture-v1",
        inventory_sha256="a" * 64,
        puzzle_count=len(rows),
        manifest_path=Path("fixture.toml"),
        inventory_path=Path("fixture.csv"),
        inventory_rows=rows,
        manifest={"collection_id": "fixture-v1", "inventory_sha256": "a" * 64},
    )


def definition(puzzle_id: str) -> dict[str, object]:
    molecule = {"atoms": [{"atom_type": "salt", "q": 0, "r": 0}], "bonds": []}
    return build_puzzle_definition(
        puzzle_id=puzzle_id,
        semantics={
            "allowed_parts": ["arm1"],
            "allowed_instructions": ["grab"],
            "reagents": [molecule],
            "products": [molecule],
            "output_scale": 1,
            "target_output_count": 6,
            "production": False,
            "production_constraints": None,
        },
    )


def puzzle_artifact(puzzle_id: str, payload: bytes) -> ArtifactRecord:
    digest = sha256_bytes(payload)
    return ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id=f"om.puzzle-artifact.sha256.{digest}",
        puzzle_id=puzzle_id,
        sha256=digest,
        byte_length=len(payload),
        artifact_format="puzzle",
        rights_status="local_fetch_only",
        object_key=f"objects/sha256/{digest[:2]}/{digest}",
    )


def provenance(record: ArtifactRecord) -> ArtifactProvenance:
    return ArtifactProvenance(
        artifact_id=record.artifact_id,
        puzzle_id=record.puzzle_id,
        source_role="artifact",
        source_id="official-game",
        source_revision="fixture",
        source_path=f"{record.puzzle_id}.puzzle",
        source_object_id=record.puzzle_id,
        source_url=None,
        author=None,
        retrieved_at="2026-08-25T00:00:00Z",
        rights_status=record.rights_status,
        observed_sha256=record.sha256,
        source_evidence_sha256=record.sha256,
        source_evidence_byte_length=record.byte_length,
        claimed_cost=None,
        claimed_cycles=None,
        claimed_area=None,
        claimed_instructions=None,
    )


def solution_bytes(puzzle_name: str) -> bytes:
    puzzle = puzzle_name.encode("utf-8")
    solution = b"fixture"
    return (
        struct.pack("<I", 7)
        + bytes([len(puzzle)])
        + puzzle
        + bytes([len(solution)])
        + solution
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
    )


def raw_output(payload: bytes) -> str:
    return json.dumps(
        {
            "format": "om-solution-base64-v1",
            "solution_base64": base64.b64encode(payload).decode("ascii"),
        },
        separators=(",", ":"),
    )


class FixtureRunner:
    def __init__(self, outputs: dict[str, str]) -> None:
        solve = solve_module()
        self.identity = solve.SolverIdentity(
            system_id="fixture-solver",
            system_revision="fixture-v1",
            generation_config_sha256="1" * 64,
        )
        self.outputs = outputs
        self.calls: list[tuple[str, int, str]] = []

    def generate(self, *, puzzle_id: str, puzzle_text: str, attempt_index: int) -> Any:
        solve = solve_module()
        self.calls.append((puzzle_id, attempt_index, puzzle_text))
        return solve.RunnerOutput(
            raw_output=self.outputs[puzzle_id],
            model_calls=1,
            input_tokens=10,
            output_tokens=5,
        )


class FixtureVerifier:
    def __init__(self, successful_artifact_id: str) -> None:
        verification = importlib.import_module("opus_corpus.verification")
        self.identity = verification.VerifierIdentity(
            verifier_implementation="fixture-verifier",
            verifier_revision="fixture-v1",
            verifier_sha256="f" * 64,
            validation_profile="fixture-v1",
        )
        self.successful_artifact_id = successful_artifact_id
        self.calls: list[VerificationInput] = []

    def verify(self, value: VerificationInput) -> VerificationResult:
        self.calls.append(value)
        success = value.puzzle_artifact_id == self.successful_artifact_id
        result_id = verification_id(
            puzzle_artifact_id=value.puzzle_artifact_id,
            solution_id=value.solution_id,
            verifier_implementation=self.identity.verifier_implementation,
            verifier_revision=self.identity.verifier_revision,
            verifier_sha256=self.identity.verifier_sha256,
            validation_profile=self.identity.validation_profile,
        )
        return VerificationResult(
            verification_id=result_id,
            puzzle_artifact_id=value.puzzle_artifact_id,
            solution_id=value.solution_id,
            verifier_implementation=self.identity.verifier_implementation,
            verifier_revision=self.identity.verifier_revision,
            verifier_sha256=self.identity.verifier_sha256,
            validation_profile=self.identity.validation_profile,
            parse_status="passed",
            simulation_status="passed" if success else "failed",
            cost=10 if success else None,
            cycles=20 if success else None,
            area=30 if success else None,
            instructions=40 if success else None,
            vanilla_constructible=None,
            record_eligible=None,
            error_code=None if success else "simulation_failed",
            error_detail=None,
        )


def fixture_inputs() -> tuple[
    CollectionDefinition,
    list[dict[str, object]],
    list[ArtifactRecord],
    list[ArtifactProvenance],
    dict[str, bytes],
]:
    value = collection()
    puzzle_ids = [row["puzzle_id"] for row in value.inventory_rows]
    definitions = [definition(puzzle_id) for puzzle_id in puzzle_ids]
    artifacts: list[ArtifactRecord] = []
    provenance_rows: list[ArtifactProvenance] = []
    artifact_bytes: dict[str, bytes] = {}
    for index, puzzle_id in enumerate(puzzle_ids[:5], start=1):
        payload = f"puzzle-bytes-{index}".encode()
        record = puzzle_artifact(puzzle_id, payload)
        artifacts.append(record)
        provenance_rows.append(provenance(record))
        artifact_bytes[record.artifact_id] = payload
    return value, definitions, artifacts, provenance_rows, artifact_bytes


def run_fixture(*, reverse_inputs: bool = False) -> tuple[Any, FixtureRunner, FixtureVerifier]:
    solve = solve_module()
    value, definitions, artifacts, provenance_rows, artifact_bytes = fixture_inputs()
    eligibility = derive_benchmark_eligibility(
        value,
        definitions=reversed(definitions) if reverse_inputs else definitions,
        artifacts=reversed(artifacts) if reverse_inputs else artifacts,
        provenance=reversed(provenance_rows) if reverse_inputs else provenance_rows,
    )
    puzzle_ids = [row["puzzle_id"] for row in value.inventory_rows]
    outputs = {
        puzzle_ids[0]: "not-json",
        puzzle_ids[1]: raw_output(b"not-a-solution"),
        puzzle_ids[2]: raw_output(solution_bytes("P999")),
        puzzle_ids[3]: raw_output(solution_bytes("P004")),
        puzzle_ids[4]: raw_output(solution_bytes("P005")),
    }
    runner = FixtureRunner(outputs)
    verifier = FixtureVerifier(artifacts[4].artifact_id)
    byte_items = list(artifact_bytes.items())
    if reverse_inputs:
        byte_items.reverse()
    result = solve.run_solve_benchmark(
        collection=value,
        eligibility=eligibility,
        definitions=reversed(definitions) if reverse_inputs else definitions,
        puzzle_artifact_bytes=dict(byte_items),
        runner=runner,
        verifier=verifier,
        attempt_budget=1,
    )
    return result, runner, verifier


def test_public_solve_path_reaches_all_wp15_outcomes_and_executable_subset() -> None:
    result, runner, verifier = run_fixture()

    assert [row["puzzle_id"] for row in result.puzzle_results] == [
        f"om.puzzle.{index:04d}" for index in range(1, 6)
    ]
    assert [row["attempts"][0]["outcome"] for row in result.puzzle_results] == [
        "output_compile_failed",
        "solution_parse_failed",
        "puzzle_solution_mismatch",
        "simulation_failed",
        "success",
    ]
    assert result.report["outcome_counts"] == {
        "output_compile_failed": 1,
        "solution_parse_failed": 1,
        "puzzle_solution_mismatch": 1,
        "simulation_failed": 1,
        "success": 1,
    }
    assert result.report["puzzle_count"] == 5
    assert result.report["solved_count"] == 1
    assert result.report["verifier_calls"] == 2
    assert result.report["benchmark"]["executable_inventory_sha256"] == (
        result.eligibility.inventory_sha256
    )
    assert result.report["benchmark"]["puzzle_serializer"] == "opus-magnum-puzzle-text"
    assert result.report["benchmark"]["puzzle_serializer_version"] == "2"
    assert result.report["benchmark"]["candidate_output_compiler"] == (
        "json-base64-solution"
    )
    assert result.report["run"]["system_id"] == "fixture-solver"
    assert result.eligibility.entries[-1].exclusion_reason == "missing_exact_artifact"
    assert [call[0] for call in runner.calls] == [
        f"om.puzzle.{index:04d}" for index in range(1, 6)
    ]
    assert len(verifier.calls) == 2
    assert all(call.solution_id.startswith("om.solution.sha256.") for call in verifier.calls)
    assert all("OPUS_MAGNUM_PUZZLE_TEXT_V2" in call[2] for call in runner.calls)


def test_solve_report_is_invariant_to_authoritative_input_order() -> None:
    first, _, _ = run_fixture()
    second, _, _ = run_fixture(reverse_inputs=True)
    assert canonical_json_bytes(first.report) == canonical_json_bytes(second.report)
    assert canonical_json_bytes(list(first.puzzle_results)) == canonical_json_bytes(
        list(second.puzzle_results)
    )


def test_solve_path_rejects_wrong_selected_artifact_bytes_before_model_execution() -> None:
    solve = solve_module()
    value, definitions, artifacts, provenance_rows, artifact_bytes = fixture_inputs()
    eligibility = derive_benchmark_eligibility(
        value,
        definitions=definitions,
        artifacts=artifacts,
        provenance=provenance_rows,
    )
    puzzle_ids = [row["puzzle_id"] for row in value.inventory_rows]
    runner = FixtureRunner({puzzle_id: "not-json" for puzzle_id in puzzle_ids[:5]})
    verifier = FixtureVerifier(artifacts[4].artifact_id)
    artifact_bytes[artifacts[0].artifact_id] = b"wrong"

    with pytest.raises(solve.SolveBenchmarkError, match="exact puzzle artifact bytes"):
        solve.run_solve_benchmark(
            collection=value,
            eligibility=eligibility,
            definitions=definitions,
            puzzle_artifact_bytes=artifact_bytes,
            runner=runner,
            verifier=verifier,
            attempt_budget=1,
        )
    assert runner.calls == []