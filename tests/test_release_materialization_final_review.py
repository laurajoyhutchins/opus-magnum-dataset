from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.release_materialization import (
    ReleaseMaterializationError,
    materialize_release_records,
)
from opus_corpus.solution_materialization import Observation
from opus_corpus.verification import verification_id


def _collection(*puzzle_ids: str) -> CollectionDefinition:
    rows = tuple(
        {
            "puzzle_id": puzzle_id,
            "display_name": f"Puzzle {index}",
            "kind": "campaign",
            "group": "campaign-1",
            "game_puzzle_id": f"P{index:03d}",
            "leaderboard_key": f"puzzle-{index}",
            "puzzle_type": "standard",
        }
        for index, puzzle_id in enumerate(puzzle_ids, start=1)
    )
    return CollectionDefinition(
        collection_id="base-game-2026-06-16",
        inventory_sha256="a" * 64,
        puzzle_count=len(rows),
        manifest_path=Path("collection.toml"),
        inventory_path=Path("collection.csv"),
        inventory_rows=rows,
        manifest={},
    )


def _puzzle(puzzle_id: str = "om.puzzle.0001") -> ArtifactRecord:
    return ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id="om.puzzle-artifact.sha256." + "a" * 64,
        puzzle_id=puzzle_id,
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


def _puzzle_provenance(puzzle: ArtifactRecord) -> ArtifactProvenance:
    return ArtifactProvenance(
        artifact_id=puzzle.artifact_id,
        puzzle_id=puzzle.puzzle_id,
        source_role="artifact",
        source_id="fixture-puzzles",
        source_revision="fixture-puzzles-rev",
        source_path=f"{puzzle.puzzle_id}.puzzle",
        source_object_id=puzzle.puzzle_id,
        source_url=None,
        author=None,
        retrieved_at="2026-08-24T00:00:00Z",
        rights_status=puzzle.rights_status,
        observed_sha256=puzzle.sha256,
        source_evidence_sha256=puzzle.sha256,
        source_evidence_byte_length=puzzle.byte_length,
        claimed_cost=None,
        claimed_cycles=None,
        claimed_area=None,
        claimed_instructions=None,
    )


def _solution_observation(solution: ArtifactRecord) -> Observation:
    return Observation(
        observation_id="om.observation.sha256." + "f" * 64,
        artifact_kind="solution",
        artifact_id=solution.artifact_id,
        puzzle_id=solution.puzzle_id,
        source_role="artifact",
        source_id="fixture-solutions",
        source_revision="fixture-solutions-rev",
        source_object_id=None,
        source_path="fixture.solution",
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
        "verifier_implementation": "fixture-verifier",
        "verifier_revision": "fixture-verifier-rev",
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


def test_release_projection_rejects_forged_observation_identity():
    puzzle = _puzzle()
    solution = _solution()
    forged = replace(
        _solution_observation(solution),
        observation_id="om.observation.sha256." + "0" * 64,
    )

    with pytest.raises(ReleaseMaterializationError, match="observation identity"):
        materialize_release_records(
            _collection(puzzle.puzzle_id),
            puzzle_artifacts=(puzzle,),
            puzzle_provenance=(_puzzle_provenance(puzzle),),
            solution_artifacts=(solution,),
            observations=(forged,),
            verifications=(_verification(puzzle, solution),),
            normalized_solutions=(),
        )


def test_release_projection_rejects_duplicate_puzzle_artifact_identity():
    first = _puzzle("om.puzzle.0001")
    second = replace(first, puzzle_id="om.puzzle.0002")

    with pytest.raises(ReleaseMaterializationError, match="puzzle artifact identity"):
        materialize_release_records(
            _collection(first.puzzle_id, second.puzzle_id),
            puzzle_artifacts=(first, second),
            puzzle_provenance=(_puzzle_provenance(second),),
            solution_artifacts=(),
            observations=(),
            verifications=(),
            normalized_solutions=(),
        )
