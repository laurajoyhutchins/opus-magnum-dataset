from __future__ import annotations

import base64
from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.config import load_config
from opus_corpus.content_store import ContentStore
from opus_corpus.hashing import canonical_json_bytes, sha256_bytes
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.normalization import normalized_solution_id
from opus_corpus.release import build_release
from opus_corpus.release_configs import CONFIG_NAMES
from opus_corpus.release_materialization import (
    ReleaseMaterializationError,
    materialize_release_inputs,
    materialize_release_records,
    write_release_inputs,
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


def _verification() -> dict[str, object]:
    identity = {
        "puzzle_artifact_id": "om.puzzle-artifact.sha256." + "a" * 64,
        "solution_id": "om.solution.sha256." + "b" * 64,
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


def _normalized() -> dict[str, object]:
    solution_id = "om.solution.sha256." + "b" * 64
    puzzle_id = "om.puzzle.0001"
    normalizer_version = "opus-solution-v1"
    return {
        "normalized_solution_id": normalized_solution_id(
            solution_id=solution_id,
            puzzle_id=puzzle_id,
            normalizer_version=normalizer_version,
        ),
        "solution_id": solution_id,
        "puzzle_id": puzzle_id,
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
    body = {
        "artifact_kind": "solution",
        "artifact_id": solution.artifact_id,
        "puzzle_id": "om.puzzle.0001",
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
    digest = sha256_bytes(canonical_json_bytes(body))
    return Observation(observation_id=f"om.observation.sha256.{digest}", **body)


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


def test_materialize_release_records_projects_canonical_entities():
    puzzle = _puzzle()
    solution = _solution()
    normalized = _normalized()

    records = materialize_release_records(
        _collection(),
        puzzle_artifacts=(puzzle,),
        puzzle_provenance=(_puzzle_provenance(puzzle),),
        solution_artifacts=(solution,),
        observations=(_observation(solution),),
        verifications=(_verification(),),
        normalized_solutions=(normalized,),
    )

    assert records["puzzles"] == [
        {
            "puzzle_id": "om.puzzle.0001",
            "display_name": "Stabilized Water",
            "kind": "campaign",
            "aliases": [
                {"system": "game_puzzle_id", "value": "P007"},
                {"system": "leaderboard_key", "value": "stabilized-water"},
            ],
            "canonical_puzzle_artifact_id": puzzle.artifact_id,
            "puzzle_sha256": puzzle.sha256,
            "puzzle_bytes": None,
            "rights_status": "local_fetch_only",
            "collection_id": "base-game-2026-06-16",
        }
    ]
    assert records["solutions"] == [
        {
            "solution_id": solution.artifact_id,
            "solution_sha256": solution.sha256,
            "puzzle_id": "om.puzzle.0001",
            "puzzle_artifact_id": puzzle.artifact_id,
            "solution_format": "solution",
            "solution_bytes": None,
            "rights_status": "local_fetch_only",
            "verified": True,
            "validation_profile": "omsim-libverify-v1",
            "verifier_revision": "verifier-rev",
            "cost": 20,
            "cycles": 40,
            "area": 10,
            "instructions": 6,
            "vanilla_constructible": None,
            "record_eligible": None,
            "normalized_solution_id": normalized["normalized_solution_id"],
            "source_count": 1,
            "collection_id": "base-game-2026-06-16",
        }
    ]
    solution_observations = [
        row for row in records["observations"] if row["artifact_kind"] == "solution"
    ]
    assert solution_observations[0]["claimed_cost"] == 999
    assert records["normalized"] == [normalized]


def test_materialize_release_records_projects_puzzle_provenance_as_observation():
    puzzle = _puzzle()

    records = materialize_release_records(
        _collection(),
        puzzle_artifacts=(puzzle,),
        puzzle_provenance=(_puzzle_provenance(puzzle),),
        solution_artifacts=(),
        observations=(),
        verifications=(),
        normalized_solutions=(),
    )

    assert len(records["observations"]) == 1
    row = records["observations"][0]
    assert row["artifact_kind"] == "puzzle"
    assert row["artifact_id"] == puzzle.artifact_id
    assert row["source_role"] == "artifact"
    assert row["source_id"] == "omsim"
    assert row["observed_sha256"] == puzzle.sha256


def test_materialize_release_records_rejects_forged_artifact_identity():
    puzzle = ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id="om.puzzle-artifact.sha256." + "0" * 64,
        puzzle_id="om.puzzle.0001",
        sha256="a" * 64,
        byte_length=11,
        artifact_format="puzzle",
        rights_status="local_fetch_only",
        object_key="objects/sha256/aa/" + "a" * 62,
    )

    with pytest.raises(ReleaseMaterializationError, match="identity"):
        materialize_release_records(
            _collection(),
            puzzle_artifacts=(puzzle,),
            solution_artifacts=(),
            observations=(),
            verifications=(),
            normalized_solutions=(),
        )


def test_materialize_release_records_includes_only_permitted_payloads(tmp_path: Path):
    store = ContentStore(tmp_path / "cache")
    puzzle_object = store.put_bytes(b"puzzle-bytes")
    solution_object = store.put_bytes(b"solution-bytes")
    puzzle = ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id=f"om.puzzle-artifact.sha256.{puzzle_object.sha256}",
        puzzle_id="om.puzzle.0001",
        sha256=puzzle_object.sha256,
        byte_length=puzzle_object.byte_length,
        artifact_format="puzzle",
        rights_status="redistributable",
        object_key=puzzle_object.object_key,
    )
    solution = ArtifactRecord(
        artifact_kind="solution",
        artifact_id=f"om.solution.sha256.{solution_object.sha256}",
        puzzle_id="om.puzzle.0001",
        sha256=solution_object.sha256,
        byte_length=solution_object.byte_length,
        artifact_format="solution",
        rights_status="local_fetch_only",
        object_key=solution_object.object_key,
    )
    identity = {
        "puzzle_artifact_id": puzzle.artifact_id,
        "solution_id": solution.artifact_id,
        "verifier_implementation": "omsim-libverify",
        "verifier_revision": "verifier-rev",
        "verifier_sha256": "c" * 64,
        "validation_profile": "omsim-libverify-v1",
    }
    verification = {
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

    records = materialize_release_records(
        _collection(),
        puzzle_artifacts=(puzzle,),
        puzzle_provenance=(_puzzle_provenance(puzzle),),
        solution_artifacts=(solution,),
        observations=(_observation(solution),),
        verifications=(verification,),
        normalized_solutions=(),
        payload_policy="include-permitted",
        store=store,
    )

    assert records["puzzles"][0]["puzzle_bytes"] == base64.b64encode(
        b"puzzle-bytes"
    ).decode("ascii")
    assert records["solutions"][0]["solution_bytes"] is None


def test_write_release_inputs_is_canonical_and_config_sorted(tmp_path: Path):
    records = {
        "puzzles": [
            {"puzzle_id": "om.puzzle.0002", "value": 2},
            {"puzzle_id": "om.puzzle.0001", "value": 1},
        ],
        "solutions": [
            {"puzzle_id": "om.puzzle.0002", "solution_id": "s2", "value": 2},
            {"puzzle_id": "om.puzzle.0001", "solution_id": "s1", "value": 1},
        ],
        "observations": [
            {"artifact_id": "b", "observation_id": "o2", "value": 2},
            {"artifact_id": "a", "observation_id": "o1", "value": 1},
        ],
        "normalized": [
            {"puzzle_id": "om.puzzle.0002", "solution_id": "s2", "value": 2},
            {"puzzle_id": "om.puzzle.0001", "solution_id": "s1", "value": 1},
        ],
    }

    write_release_inputs(records, tmp_path)

    assert (tmp_path / "puzzles.jsonl").read_text(encoding="utf-8") == (
        '{"puzzle_id":"om.puzzle.0001","value":1}\n'
        '{"puzzle_id":"om.puzzle.0002","value":2}\n'
    )
    assert (tmp_path / "solutions.jsonl").read_text(encoding="utf-8") == (
        '{"puzzle_id":"om.puzzle.0001","solution_id":"s1","value":1}\n'
        '{"puzzle_id":"om.puzzle.0002","solution_id":"s2","value":2}\n'
    )
    assert (tmp_path / "observations.jsonl").read_text(encoding="utf-8") == (
        '{"artifact_id":"a","observation_id":"o1","value":1}\n'
        '{"artifact_id":"b","observation_id":"o2","value":2}\n'
    )
    assert (tmp_path / "normalized.jsonl").read_text(encoding="utf-8") == (
        '{"puzzle_id":"om.puzzle.0001","solution_id":"s1","value":1}\n'
        '{"puzzle_id":"om.puzzle.0002","solution_id":"s2","value":2}\n'
    )


def test_materialize_release_inputs_rebuilds_identical_logical_release(tmp_path: Path):
    puzzle = _puzzle()
    solution = _solution()
    kwargs = {
        "puzzle_artifacts": (puzzle,),
        "puzzle_provenance": (_puzzle_provenance(puzzle),),
        "solution_artifacts": (solution,),
        "observations": (_observation(solution),),
        "verifications": (_verification(),),
        "normalized_solutions": (_normalized(),),
    }
    input_a = tmp_path / "input-a"
    input_b = tmp_path / "input-b"
    input_a.mkdir()
    input_b.mkdir()

    metadata_template = {
        "release_kind": "fixture",
        "corpus_schema_version": "0.1",
        "coverage": {"summary": "WP-11 deterministic projection fixture."},
        "known_limitations": [],
    }
    template_bytes = canonical_json_bytes(metadata_template) + b"\n"
    (input_a / "release-metadata.json").write_bytes(template_bytes)
    (input_b / "release-metadata.json").write_bytes(template_bytes)

    materialize_release_inputs(_collection(), input_a, **kwargs)
    materialize_release_inputs(_collection(), input_b, **kwargs)

    assert (input_a / "release-metadata.json").read_bytes() == (
        input_b / "release-metadata.json"
    ).read_bytes()
    for config_name in CONFIG_NAMES:
        assert (input_a / f"{config_name}.jsonl").read_bytes() == (
            input_b / f"{config_name}.jsonl"
        ).read_bytes()

    config = load_config("corpus.toml")
    manifest_a = build_release(
        _collection(),
        input_a,
        tmp_path / "release-a",
        config,
        "metadata-only",
        coverage_policy="subset",
    )
    manifest_b = build_release(
        _collection(),
        input_b,
        tmp_path / "release-b",
        config,
        "metadata-only",
        coverage_policy="subset",
    )

    assert manifest_a.logical_release_sha256 == manifest_b.logical_release_sha256
