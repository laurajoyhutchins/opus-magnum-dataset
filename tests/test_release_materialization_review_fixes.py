from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.hashing import canonical_json_bytes, sha256_bytes
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.normalization import normalized_solution_id
from opus_corpus.release_materialization import (
    ReleaseMaterializationError,
    materialize_release_inputs,
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


def _puzzle_provenance(puzzle: ArtifactRecord) -> ArtifactProvenance:
    return ArtifactProvenance(
        artifact_id=puzzle.artifact_id,
        puzzle_id=puzzle.puzzle_id,
        source_role="artifact",
        source_id="omsim",
        source_revision="omsim-rev",
        source_path="test/puzzle/campaign/P007.puzzle",
        source_object_id="P007",
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


def _observation(solution: ArtifactRecord) -> Observation:
    body = {
        "artifact_kind": "solution",
        "artifact_id": solution.artifact_id,
        "puzzle_id": solution.puzzle_id,
        "source_role": "artifact",
        "source_id": "fixture",
        "source_revision": "fixture-rev",
        "source_object_id": None,
        "source_path": "solutions/example.solution",
        "associated_artifact_path": None,
        "source_declared_puzzle_id": None,
        "source_url": None,
        "author": None,
        "retrieved_at": "2026-08-24T00:00:00Z",
        "claimed_cost": None,
        "claimed_cycles": None,
        "claimed_area": None,
        "claimed_instructions": None,
        "observed_sha256": solution.sha256,
        "source_evidence_sha256": solution.sha256,
        "source_evidence_byte_length": solution.byte_length,
        "rights_status": solution.rights_status,
        "importer_version": "fixture-v1",
    }
    digest = sha256_bytes(canonical_json_bytes(body))
    return Observation(observation_id=f"om.observation.sha256.{digest}", **body)


def _reidentified(observation: Observation, **changes: object) -> Observation:
    changed = replace(observation, **changes)
    body = asdict(changed)
    body.pop("observation_id")
    digest = sha256_bytes(canonical_json_bytes(body))
    return replace(changed, observation_id=f"om.observation.sha256.{digest}")


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


def _normalized(solution: ArtifactRecord) -> dict[str, object]:
    version = "opus-solution-v1"
    return {
        "normalized_solution_id": normalized_solution_id(
            solution_id=solution.artifact_id,
            puzzle_id=solution.puzzle_id,
            normalizer_version=version,
        ),
        "solution_id": solution.artifact_id,
        "puzzle_id": solution.puzzle_id,
        "normalizer_version": version,
        "parts": [],
        "tracks": [],
        "programs": [],
        "summaries": {
            "part_count": 0,
            "track_count": 0,
            "track_hex_count": 0,
            "program_count": 0,
            "instruction_count": 0,
            "part_type_histogram": {},
            "opcode_histogram": {},
        },
    }


def _template(path: Path, **extra: object) -> None:
    path.mkdir(parents=True, exist_ok=True)
    metadata = {
        "release_kind": "fixture",
        "corpus_schema_version": "0.1",
        "coverage": {"summary": "WP-11 review fixture."},
        "known_limitations": [],
        **extra,
    }
    (path / "release-metadata.json").write_bytes(canonical_json_bytes(metadata) + b"\n")


def test_release_projection_requires_puzzle_provenance():
    puzzle = _puzzle()

    with pytest.raises(ReleaseMaterializationError, match="puzzle.*provenance"):
        materialize_release_records(
            _collection(),
            puzzle_artifacts=(puzzle,),
            solution_artifacts=(),
            observations=(),
            verifications=(),
            normalized_solutions=(),
        )


def test_release_projection_rejects_solution_observation_with_wrong_puzzle():
    puzzle = _puzzle()
    solution = _solution()
    observation = _reidentified(_observation(solution), puzzle_id="om.puzzle.0002")

    with pytest.raises(ReleaseMaterializationError, match="observation.*puzzle"):
        materialize_release_records(
            _collection(),
            puzzle_artifacts=(puzzle,),
            puzzle_provenance=(_puzzle_provenance(puzzle),),
            solution_artifacts=(solution,),
            observations=(observation,),
            verifications=(_verification(puzzle, solution),),
            normalized_solutions=(),
        )


def test_release_projection_rejects_solution_observation_with_wrong_hash():
    puzzle = _puzzle()
    solution = _solution()
    observation = _reidentified(_observation(solution), observed_sha256="0" * 64)

    with pytest.raises(ReleaseMaterializationError, match="observation.*sha256"):
        materialize_release_records(
            _collection(),
            puzzle_artifacts=(puzzle,),
            puzzle_provenance=(_puzzle_provenance(puzzle),),
            solution_artifacts=(solution,),
            observations=(observation,),
            verifications=(_verification(puzzle, solution),),
            normalized_solutions=(),
        )


def test_release_materialization_derives_manifest_provenance(tmp_path: Path):
    puzzle = _puzzle()
    solution = _solution()
    output = tmp_path / "input"
    _template(output)

    materialize_release_inputs(
        _collection(),
        output,
        puzzle_artifacts=(puzzle,),
        puzzle_provenance=(_puzzle_provenance(puzzle),),
        solution_artifacts=(solution,),
        observations=(_observation(solution),),
        verifications=(_verification(puzzle, solution),),
        normalized_solutions=(_normalized(solution),),
    )

    metadata = json.loads((output / "release-metadata.json").read_text(encoding="utf-8"))
    assert metadata["verifier_revision"] == "verifier-rev"
    assert metadata["verifier_sha256"] == "c" * 64
    assert metadata["validation_profile"] == "omsim-libverify-v1"
    assert metadata["normalizer_version"] == "opus-solution-v1"
    assert metadata["source_classes"] == [
        {"source_id": "fixture", "revision": "fixture-rev"},
        {"source_id": "omsim", "revision": "omsim-rev"},
    ]


def test_release_materialization_rejects_hand_authored_derived_provenance(tmp_path: Path):
    puzzle = _puzzle()
    solution = _solution()
    output = tmp_path / "input"
    _template(output, verifier_revision="bogus")

    with pytest.raises(ReleaseMaterializationError, match="derived release metadata"):
        materialize_release_inputs(
            _collection(),
            output,
            puzzle_artifacts=(puzzle,),
            puzzle_provenance=(_puzzle_provenance(puzzle),),
            solution_artifacts=(solution,),
            observations=(_observation(solution),),
            verifications=(_verification(puzzle, solution),),
            normalized_solutions=(_normalized(solution),),
        )
