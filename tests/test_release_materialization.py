from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.content_store import ContentStore
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.normalization import normalized_solution_id
from opus_corpus.observations import observation_id
from opus_corpus.puzzle_definition import build_puzzle_definition
from opus_corpus.puzzle_materialization import materialize_puzzle_provenance_observations
from opus_corpus.release_materialization import (
    ReleaseMaterializationError,
    materialize_release_inputs,
    materialize_release_records,
    write_release_inputs,
)
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


def _artifact(
    kind: str,
    digest: str,
    *,
    rights_status: str = "local_fetch_only",
    byte_length: int = 11,
) -> ArtifactRecord:
    prefix = "om.puzzle-artifact.sha256." if kind == "puzzle" else "om.solution.sha256."
    return ArtifactRecord(
        artifact_kind=kind,
        artifact_id=prefix + digest,
        puzzle_id="om.puzzle.0001",
        sha256=digest,
        byte_length=byte_length,
        artifact_format=kind,
        rights_status=rights_status,
        object_key=f"objects/sha256/{digest[:2]}/{digest[2:]}",
    )


def _puzzle() -> ArtifactRecord:
    return _artifact("puzzle", "a" * 64)


def _solution() -> ArtifactRecord:
    return _artifact("solution", "b" * 64, byte_length=22)


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


def _puzzle_observation(puzzle: ArtifactRecord) -> dict[str, object]:
    return materialize_puzzle_provenance_observations(
        (puzzle,),
        (_puzzle_provenance(puzzle),),
    )[0]


def _solution_observation(solution: ArtifactRecord) -> dict[str, object]:
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
        "author": "fixture",
        "retrieved_at": "2026-08-24T00:00:00Z",
        "claimed_cost": 999,
        "claimed_cycles": 999,
        "claimed_area": 999,
        "claimed_instructions": 999,
        "observed_sha256": solution.sha256,
        "source_evidence_sha256": solution.sha256,
        "source_evidence_byte_length": solution.byte_length,
        "rights_status": solution.rights_status,
        "importer_version": "fixture-v1",
    }
    return {"observation_id": observation_id(body), **body}


def _definition(
    artifacts: tuple[ArtifactRecord, ...],
    observations: tuple[dict[str, object], ...],
) -> dict[str, object]:
    molecule = {
        "atoms": [{"atom_type": "salt", "q": 0, "r": 0}],
        "bonds": [],
    }
    return build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics={
            "allowed_parts": ["arm1", "bonder"],
            "allowed_instructions": ["grab", "drop"],
            "reagents": [molecule],
            "products": [molecule],
            "output_scale": 1,
            "target_output_count": 6,
            "production": False,
            "production_constraints": None,
        },
        source_observation_ids=[row["observation_id"] for row in observations],
        puzzle_artifact_ids=[artifact.artifact_id for artifact in artifacts],
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


def _normalized(solution: ArtifactRecord) -> dict[str, object]:
    normalizer_version = "opus-solution-v1"
    return {
        "normalized_solution_id": normalized_solution_id(
            solution_id=solution.artifact_id,
            puzzle_id=solution.puzzle_id,
            normalizer_version=normalizer_version,
        ),
        "solution_id": solution.artifact_id,
        "puzzle_id": solution.puzzle_id,
        "normalizer_version": normalizer_version,
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
        "tracks": [
            {
                "track_id": "track-1",
                "coordinates": [{"x": 0, "y": 0}],
            }
        ],
        "programs": [
            {
                "arm_id": "arm-1",
                "instructions": [{"cycle": 0, "opcode": "grab"}],
            }
        ],
        "summaries": {
            "part_count": 1,
            "track_count": 1,
            "track_hex_count": 1,
            "program_count": 1,
            "instruction_count": 1,
            "part_type_histogram": {"arm1": 1},
            "opcode_histogram": {"grab": 1},
        },
    }


def _records_inputs():
    puzzle = _puzzle()
    puzzle_observation = _puzzle_observation(puzzle)
    definition = _definition((puzzle,), (puzzle_observation,))
    solution = _solution()
    return (
        puzzle,
        definition,
        puzzle_observation,
        solution,
        _solution_observation(solution),
        _verification(puzzle, solution),
        _normalized(solution),
    )


def test_materialize_release_records_projects_semantic_puzzle_and_exact_solution_lineage():
    puzzle, definition, puzzle_obs, solution, solution_obs, verification, normalized = (
        _records_inputs()
    )

    records = materialize_release_records(
        _collection(),
        puzzle_definitions=(definition,),
        puzzle_artifacts=(puzzle,),
        solution_artifacts=(solution,),
        observations=(puzzle_obs, solution_obs),
        verifications=(verification,),
        normalized_solutions=(normalized,),
    )

    assert records["puzzles"] == [
        {
            **definition,
            "display_name": "Stabilized Water",
            "kind": "campaign",
            "aliases": [
                {"system": "game_puzzle_id", "value": "P007"},
                {"system": "leaderboard_key", "value": "stabilized-water"},
            ],
            "collection_id": "base-game-2026-06-16",
        }
    ]
    assert "puzzle_bytes" not in records["puzzles"][0]
    assert "puzzle_sha256" not in records["puzzles"][0]
    assert records["solutions"][0]["puzzle_artifact_id"] == puzzle.artifact_id
    assert records["solutions"][0]["normalized_solution_id"] == normalized[
        "normalized_solution_id"
    ]
    assert records["solutions"][0]["source_count"] == 1
    assert {row["observation_id"] for row in records["observations"]} == {
        puzzle_obs["observation_id"],
        solution_obs["observation_id"],
    }


def test_release_requires_provenance_for_each_exact_puzzle_artifact():
    puzzle, definition, _puzzle_obs, solution, solution_obs, verification, normalized = (
        _records_inputs()
    )

    with pytest.raises(ReleaseMaterializationError, match="no provenance observation"):
        materialize_release_records(
            _collection(),
            puzzle_definitions=(definition,),
            puzzle_artifacts=(puzzle,),
            solution_artifacts=(solution,),
            observations=(solution_obs,),
            verifications=(verification,),
            normalized_solutions=(normalized,),
        )


def test_release_rejects_exact_artifact_not_bound_to_semantic_definition():
    puzzle = _puzzle()
    puzzle_obs = _puzzle_observation(puzzle)
    definition = _definition((), (puzzle_obs,))

    with pytest.raises(ReleaseMaterializationError, match="not bound to PuzzleDefinition"):
        materialize_release_records(
            _collection(),
            puzzle_definitions=(definition,),
            puzzle_artifacts=(puzzle,),
            solution_artifacts=(),
            observations=(puzzle_obs,),
            verifications=(),
            normalized_solutions=(),
        )


def test_equivalent_exact_artifacts_can_share_one_semantic_definition():
    first = _puzzle()
    second = _artifact("puzzle", "d" * 64)
    first_obs = _puzzle_observation(first)
    second_obs = _puzzle_observation(second)
    definition = _definition((first, second), (first_obs, second_obs))
    solution = _solution()

    records = materialize_release_records(
        _collection(),
        puzzle_definitions=(definition,),
        puzzle_artifacts=(first, second),
        solution_artifacts=(solution,),
        observations=(first_obs, second_obs, _solution_observation(solution)),
        verifications=(_verification(first, solution),),
        normalized_solutions=(_normalized(solution),),
    )

    assert records["puzzles"][0]["puzzle_artifact_ids"] == sorted(
        [first.artifact_id, second.artifact_id]
    )
    assert records["solutions"][0]["puzzle_artifact_id"] == first.artifact_id


def test_release_rejects_forged_artifact_identity():
    puzzle = _puzzle()
    forged = ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id="om.puzzle-artifact.sha256." + "0" * 64,
        puzzle_id=puzzle.puzzle_id,
        sha256=puzzle.sha256,
        byte_length=puzzle.byte_length,
        artifact_format=puzzle.artifact_format,
        rights_status=puzzle.rights_status,
        object_key=puzzle.object_key,
    )
    definition = _definition((forged,), ())

    with pytest.raises(ReleaseMaterializationError, match="identity"):
        materialize_release_records(
            _collection(),
            puzzle_definitions=(definition,),
            puzzle_artifacts=(forged,),
            solution_artifacts=(),
            observations=(),
            verifications=(),
            normalized_solutions=(),
        )


def test_release_rejects_forged_observation_identity():
    puzzle, definition, puzzle_obs, *_ = _records_inputs()
    forged = {**puzzle_obs, "observation_id": "forged-observation"}

    with pytest.raises(ReleaseMaterializationError, match="observation identity"):
        materialize_release_records(
            _collection(),
            puzzle_definitions=(definition,),
            puzzle_artifacts=(puzzle,),
            solution_artifacts=(),
            observations=(forged,),
            verifications=(),
            normalized_solutions=(),
        )


def test_release_rejects_forged_verification_identity():
    puzzle, definition, puzzle_obs, solution, solution_obs, verification, normalized = (
        _records_inputs()
    )
    forged = {**verification, "verification_id": "om.verification." + "0" * 64}

    with pytest.raises(ReleaseMaterializationError, match="Verification identity"):
        materialize_release_records(
            _collection(),
            puzzle_definitions=(definition,),
            puzzle_artifacts=(puzzle,),
            solution_artifacts=(solution,),
            observations=(puzzle_obs, solution_obs),
            verifications=(forged,),
            normalized_solutions=(normalized,),
        )


def test_release_rejects_forged_normalized_identity():
    puzzle, definition, puzzle_obs, solution, solution_obs, verification, normalized = (
        _records_inputs()
    )
    forged = {**normalized, "normalized_solution_id": "forged-normalized"}

    with pytest.raises(ReleaseMaterializationError, match="normalized solution identity"):
        materialize_release_records(
            _collection(),
            puzzle_definitions=(definition,),
            puzzle_artifacts=(puzzle,),
            solution_artifacts=(solution,),
            observations=(puzzle_obs, solution_obs),
            verifications=(verification,),
            normalized_solutions=(forged,),
        )


def test_include_permitted_emits_solution_payload_but_never_puzzle_payload(tmp_path: Path):
    store = ContentStore(tmp_path / "cache")
    puzzle_object = store.put_bytes(b"puzzle-bytes")
    solution_object = store.put_bytes(b"solution-bytes")
    puzzle = _artifact(
        "puzzle",
        puzzle_object.sha256,
        rights_status="redistributable",
        byte_length=puzzle_object.byte_length,
    )
    solution = _artifact(
        "solution",
        solution_object.sha256,
        rights_status="redistributable",
        byte_length=solution_object.byte_length,
    )
    puzzle_obs = _puzzle_observation(puzzle)
    definition = _definition((puzzle,), (puzzle_obs,))

    records = materialize_release_records(
        _collection(),
        puzzle_definitions=(definition,),
        puzzle_artifacts=(puzzle,),
        solution_artifacts=(solution,),
        observations=(puzzle_obs, _solution_observation(solution)),
        verifications=(_verification(puzzle, solution),),
        normalized_solutions=(),
        payload_policy="include-permitted",
        store=store,
    )

    assert "puzzle_bytes" not in records["puzzles"][0]
    assert records["solutions"][0]["solution_bytes"] == base64.b64encode(
        b"solution-bytes"
    ).decode("ascii")


def test_materialize_release_inputs_derives_metadata_and_writes_canonical_inputs(
    tmp_path: Path,
):
    puzzle, definition, puzzle_obs, solution, solution_obs, verification, normalized = (
        _records_inputs()
    )
    output = tmp_path / "release-inputs"
    output.mkdir()
    (output / "release-metadata.json").write_text(
        json.dumps({"corpus_schema_version": "0.1"}) + "\n",
        encoding="utf-8",
    )

    records = materialize_release_inputs(
        _collection(),
        output,
        puzzle_definitions=(definition,),
        puzzle_artifacts=(puzzle,),
        solution_artifacts=(solution,),
        observations=(puzzle_obs, solution_obs),
        verifications=(verification,),
        normalized_solutions=(normalized,),
    )

    metadata = json.loads((output / "release-metadata.json").read_text(encoding="utf-8"))
    assert metadata["verifier_revision"] == "verifier-rev"
    assert metadata["validation_profile"] == "omsim-libverify-v1"
    assert metadata["normalizer_version"] == "opus-solution-v1"
    assert metadata["source_classes"] == [
        {"source_id": "fixture", "revision": "fixture-rev"},
        {"source_id": "omsim", "revision": "omsim-rev"},
    ]
    assert json.loads((output / "puzzles.jsonl").read_text(encoding="utf-8")) == records[
        "puzzles"
    ][0]


def test_write_release_inputs_is_config_and_row_sorted(tmp_path: Path):
    records = {
        "puzzles": [{"puzzle_id": "b"}, {"puzzle_id": "a"}],
        "solutions": [
            {"puzzle_id": "b", "solution_id": "s2"},
            {"puzzle_id": "a", "solution_id": "s1"},
        ],
        "observations": [
            {"artifact_id": "b", "observation_id": "o2"},
            {"artifact_id": "a", "observation_id": "o1"},
        ],
        "normalized": [
            {"puzzle_id": "b", "solution_id": "s2"},
            {"puzzle_id": "a", "solution_id": "s1"},
        ],
    }

    write_release_inputs(records, tmp_path)

    assert (tmp_path / "puzzles.jsonl").read_text(encoding="utf-8") == (
        '{"puzzle_id":"a"}\n{"puzzle_id":"b"}\n'
    )
