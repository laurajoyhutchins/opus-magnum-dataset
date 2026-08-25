from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.ingestion import ArtifactRecord
from opus_corpus.normalization import normalized_solution_id
from opus_corpus.release_materialization import (
    ReleaseMaterializationError,
    materialize_release_records,
)
from opus_corpus.solution_materialization import Observation
from opus_corpus.verification import verification_id


def _collection() -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="base-game-2026-06-16",
        inventory_sha256="a" * 64,
        puzzle_count=1,
        manifest_path=Path("collection.toml"),
        inventory_path=Path("collection.csv"),
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0001",
                "display_name": "Stabilized Water",
                "kind": "campaign",
                "group": "campaign-1",
                "game_puzzle_id": "P007",
                "leaderboard_key": "stabilized-water",
                "puzzle_type": "standard",
            },
        ),
        manifest={},
    )


def _puzzle() -> ArtifactRecord:
    return ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id="om.puzzle-artifact.sha256." + "a" * 64,
        puzzle_id="om.puzzle.0001",
        sha256="a" * 64,
        byte_length=11,
        artifact_format="puzzle",
        rights_status="local_fetch_only",
        object_key="objects/sha256/aa/" + "a" * 62,
    )


def _solution() -> ArtifactRecord:
    return ArtifactRecord(
        artifact_kind="solution",
        artifact_id="om.solution.sha256." + "b" * 64,
        puzzle_id="om.puzzle.0001",
        sha256="b" * 64,
        byte_length=22,
        artifact_format="solution",
        rights_status="local_fetch_only",
        object_key="objects/sha256/bb/" + "b" * 62,
    )


def _observation(solution: ArtifactRecord) -> Observation:
    return Observation(
        observation_id="om.observation.sha256." + "f" * 64,
        artifact_kind="solution",
        artifact_id=solution.artifact_id,
        puzzle_id=solution.puzzle_id,
        source_role="artifact",
        source_id="fixture",
        source_revision="fixture-rev",
        source_object_id=None,
        source_path="solutions/example.solution",
        associated_artifact_path=None,
        source_declared_puzzle_id=None,
        source_url=None,
        author=None,
        retrieved_at="2026-08-24T00:00:00Z",
        claimed_cost=None,
        claimed_cycles=None,
        claimed_area=None,
        claimed_instructions=None,
        observed_sha256=solution.sha256,
        source_evidence_sha256=solution.sha256,
        source_evidence_byte_length=solution.byte_length,
        rights_status=solution.rights_status,
        importer_version="fixture-v1",
    )


def _verification(puzzle: ArtifactRecord, solution: ArtifactRecord) -> dict[str, object]:
    identity = {
        "puzzle_artifact_id": puzzle.artifact_id,
        "solution_id": solution.artifact_id,
        "verifier_implementation": "omsim-libverify",
        "verifier_revision": "verifier-rev",
        "verifier_sha256": "c" * 64,
        "validation_profile": "omsim-libverify-v1",
    }
    return {
        "verification_id": verification_id(**identity),
        **identity,
        "parse_status": "passed",
        "simulation_status": "passed",
        "cost": 20,
        "cycles": 40,
        "area": 10,
        "instructions": 6,
        "vanilla_constructible": None,
        "record_eligible": None,
        "error_code": None,
        "error_detail": None,
    }


def _project(*, verification: dict[str, object], normalized_solutions=()):
    puzzle = _puzzle()
    solution = _solution()
    return materialize_release_records(
        _collection(),
        puzzle_artifacts=(puzzle,),
        solution_artifacts=(solution,),
        observations=(_observation(solution),),
        verifications=(verification,),
        normalized_solutions=normalized_solutions,
    )


def test_release_projection_rejects_schema_invalid_verification():
    puzzle = _puzzle()
    solution = _solution()
    verification = {**_verification(puzzle, solution), "parse_status": "bogus"}

    with pytest.raises(ReleaseMaterializationError, match="Verification record"):
        _project(verification=verification)


def test_release_projection_rejects_forged_verification_identity():
    puzzle = _puzzle()
    solution = _solution()
    verification = {
        **_verification(puzzle, solution),
        "verification_id": "om.verification." + "0" * 64,
    }

    with pytest.raises(ReleaseMaterializationError, match="Verification identity"):
        _project(verification=verification)


def test_release_projection_rejects_forged_normalized_identity():
    puzzle = _puzzle()
    solution = _solution()
    verification = _verification(puzzle, solution)
    normalized = {
        "normalized_solution_id": "om.normalized-solution." + "0" * 64,
        "solution_id": solution.artifact_id,
        "puzzle_id": solution.puzzle_id,
        "normalizer_version": "opus-solution-v1",
        "parts": [
            {
                "part_id": "arm-1",
                "type": "arm1",
                "x": 0,
                "y": 0,
                "rotation": 0,
                "parameters": {"length": 1},
            }
        ],
        "tracks": [],
        "programs": [],
        "summaries": {
            "part_count": 1,
            "track_count": 0,
            "track_hex_count": 0,
            "program_count": 0,
            "instruction_count": 0,
            "part_type_histogram": {"arm1": 1},
            "opcode_histogram": {},
        },
    }
    assert normalized["normalized_solution_id"] != normalized_solution_id(
        solution_id=solution.artifact_id,
        puzzle_id=solution.puzzle_id,
        normalizer_version="opus-solution-v1",
    )

    with pytest.raises(ReleaseMaterializationError, match="normalized solution identity"):
        _project(verification=verification, normalized_solutions=(normalized,))
