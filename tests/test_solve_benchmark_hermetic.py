from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from opus_corpus.benchmark_eligibility import derive_benchmark_eligibility
from opus_corpus.collections import CollectionDefinition
from opus_corpus.hashing import canonical_json_bytes, sha256_bytes
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.libverify import LibverifyVerifier
from opus_corpus.puzzle_definition import build_puzzle_definition
from opus_corpus.solve_benchmark import RunnerOutput, SolverIdentity, run_solve_benchmark

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "solve-benchmark-v0.1"
FIXTURE_PATH = FIXTURE_ROOT / "fixture.json"


def _load_fixture() -> dict[str, Any]:
    assert FIXTURE_PATH.is_file(), "repository-owned hermetic Solve fixture is missing"
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _definition(puzzle_id: str) -> dict[str, object]:
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


def _fixture_inputs(data: dict[str, Any]) -> tuple[
    CollectionDefinition,
    list[dict[str, object]],
    list[ArtifactRecord],
    list[ArtifactProvenance],
    dict[str, bytes],
]:
    rows = tuple(
        {
            "puzzle_id": puzzle["puzzle_id"],
            "display_name": puzzle["display_name"],
            "kind": "fixture",
            "group": "hermetic-solve-v0.1",
            "game_puzzle_id": puzzle["game_puzzle_id"],
            "leaderboard_key": f"FIXTURE_{index}",
            "puzzle_type": "normal",
        }
        for index, puzzle in enumerate(data["puzzles"], start=1)
    )
    inventory_sha256 = sha256_bytes(canonical_json_bytes(rows))
    manifest = {
        "collection_id": data["collection_id"],
        "inventory_sha256": inventory_sha256,
        "test_only": True,
    }
    collection = CollectionDefinition(
        collection_id=data["collection_id"],
        inventory_sha256=inventory_sha256,
        puzzle_count=len(rows),
        manifest_path=FIXTURE_ROOT / "manifest.toml",
        inventory_path=FIXTURE_ROOT / "inventory.csv",
        inventory_rows=rows,
        manifest=manifest,
    )
    definitions = [_definition(puzzle["puzzle_id"]) for puzzle in data["puzzles"]]
    artifacts: list[ArtifactRecord] = []
    provenance_rows: list[ArtifactProvenance] = []
    artifact_bytes: dict[str, bytes] = {}
    for puzzle in data["puzzles"]:
        encoded = puzzle.get("puzzle_bytes_base64")
        if encoded is None:
            continue
        payload = base64.b64decode(encoded, validate=True)
        digest = sha256_bytes(payload)
        record = ArtifactRecord(
            artifact_kind="puzzle",
            artifact_id=f"om.puzzle-artifact.sha256.{digest}",
            puzzle_id=puzzle["puzzle_id"],
            sha256=digest,
            byte_length=len(payload),
            artifact_format="puzzle",
            rights_status="local_fetch_only",
            object_key=f"objects/sha256/{digest[:2]}/{digest}",
        )
        artifacts.append(record)
        artifact_bytes[record.artifact_id] = payload
        provenance_rows.append(
            ArtifactProvenance(
                artifact_id=record.artifact_id,
                puzzle_id=record.puzzle_id,
                source_role="artifact",
                source_id="hermetic-test-fixture",
                source_revision="v1",
                source_path=f"fixtures/solve-benchmark-v0.1/{record.puzzle_id}.puzzle",
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
        )
    return collection, definitions, artifacts, provenance_rows, artifact_bytes


class FixtureRunner:
    def __init__(self, data: dict[str, Any]) -> None:
        runner = data["runner"]
        self.identity = SolverIdentity(
            system_id=runner["system_id"],
            system_revision=runner["system_revision"],
            generation_config_sha256=runner["generation_config_sha256"],
        )
        self.outputs = {
            puzzle["puzzle_id"]: puzzle["raw_output"]
            for puzzle in data["puzzles"]
            if puzzle.get("raw_output") is not None
        }
        self.calls: list[str] = []

    def generate(self, *, puzzle_id: str, puzzle_text: str, attempt_index: int) -> RunnerOutput:
        self.calls.append(puzzle_id)
        assert "OPUS_MAGNUM_PUZZLE_TEXT_V2" in puzzle_text
        assert attempt_index == 1
        return RunnerOutput(
            raw_output=self.outputs[puzzle_id],
            model_calls=1,
            input_tokens=10,
            output_tokens=5,
        )


class FixtureLibverifyBackend:
    def __init__(self, data: dict[str, Any], simulation_failure_bytes: bytes) -> None:
        verifier = data["verifier"]
        self.binary_sha256 = verifier["binary_sha256"]
        self.metrics = verifier["metrics"]
        self.simulation_failure_bytes = simulation_failure_bytes
        self.current_puzzle = b""
        self.current_error: tuple[str, str, int, int, int] | None = None
        self.created: list[tuple[bytes, bytes]] = []
        self.cycle_limits: list[int] = []
        self.destroyed = 0

    def create(self, puzzle_bytes: bytes, solution_bytes: bytes) -> object:
        self.current_puzzle = puzzle_bytes
        self.current_error = None
        self.created.append((puzzle_bytes, solution_bytes))
        return object()

    def destroy(self, handle: object) -> None:
        self.destroyed += 1

    def set_cycle_limit(self, handle: object, cycle_limit: int) -> None:
        self.cycle_limits.append(cycle_limit)

    def error(self, handle: object) -> str | None:
        return None if self.current_error is None else self.current_error[1]

    def error_source(self, handle: object) -> str | None:
        return None if self.current_error is None else self.current_error[0]

    def error_cycle(self, handle: object) -> int:
        return 0 if self.current_error is None else self.current_error[2]

    def error_location(self, handle: object) -> tuple[int, int]:
        if self.current_error is None:
            return 0, 0
        return self.current_error[3], self.current_error[4]

    def evaluate_metric(self, handle: object, name: str) -> int:
        if self.current_puzzle == self.simulation_failure_bytes and name == "cycles":
            self.current_error = ("simulation", "fixture collision", 12, -3, 4)
            return -1
        return int(self.metrics[name])


def _run(data: dict[str, Any], *, reverse_inputs: bool = False) -> tuple[Any, Any, Any]:
    collection, definitions, artifacts, provenance_rows, artifact_bytes = _fixture_inputs(data)
    eligibility = derive_benchmark_eligibility(
        collection,
        definitions=reversed(definitions) if reverse_inputs else definitions,
        artifacts=reversed(artifacts) if reverse_inputs else artifacts,
        provenance=reversed(provenance_rows) if reverse_inputs else provenance_rows,
    )
    simulation_id = data["verifier"]["simulation_failure_puzzle_id"]
    simulation_record = next(record for record in artifacts if record.puzzle_id == simulation_id)
    backend = FixtureLibverifyBackend(data, artifact_bytes[simulation_record.artifact_id])
    result = run_solve_benchmark(
        collection=collection,
        eligibility=eligibility,
        definitions=reversed(definitions) if reverse_inputs else definitions,
        puzzle_artifact_bytes=dict(reversed(list(artifact_bytes.items())))
        if reverse_inputs
        else artifact_bytes,
        runner=FixtureRunner(data),
        verifier=LibverifyVerifier(backend),
        attempt_budget=1,
    )
    return result, backend, eligibility


def test_repository_owned_hermetic_solve_fixture_exercises_public_v01_path() -> None:
    data = _load_fixture()
    assert data["schema"] == "solve-benchmark-hermetic-fixture-v1"
    assert data["test_only"] is True
    assert FIXTURE_ROOT.parent.name == "fixtures"

    result, backend, eligibility = _run(data)
    expected = data["expected"]
    outcomes = [row["attempts"][0]["outcome"] for row in result.puzzle_results]
    assert outcomes == expected["outcomes"]
    assert result.report["outcome_counts"] == expected["outcome_counts"]
    assert result.report["puzzle_count"] == 5
    assert result.report["solved_count"] == 1
    assert result.report["verifier_calls"] == 2
    assert eligibility.entries[-1].eligible is False
    assert eligibility.entries[-1].exclusion_reason == "missing_exact_artifact"
    assert len(backend.created) == 2
    assert backend.destroyed == 2
    assert backend.cycle_limits == [150000, 150000]

    reordered, _, _ = _run(data, reverse_inputs=True)
    report_bytes = canonical_json_bytes(result.report)
    assert canonical_json_bytes(reordered.report) == report_bytes
    assert result.report["benchmark"]["benchmark_id"] == expected["benchmark_id"]
    assert result.report["run"]["run_id"] == expected["run_id"]
    assert sha256_bytes(report_bytes) == expected["report_sha256"]
