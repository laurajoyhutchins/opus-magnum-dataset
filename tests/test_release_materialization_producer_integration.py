from __future__ import annotations

import struct
from pathlib import Path

from opus_corpus.collections import CollectionDefinition
from opus_corpus.content_store import ContentStore
from opus_corpus.hashing import canonical_json_bytes, sha256_bytes
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.release_materialization import materialize_release_records
from opus_corpus.solution_materialization import Observation
from opus_corpus.solution_normalizer import (
    OpusSolutionNormalizer,
    normalize_solution_artifacts,
)
from opus_corpus.verification import VerificationInput, VerificationResult, verification_id
from opus_corpus.verification_materialization import materialize_verifications


class _FixtureVerifier:
    def verify(self, value: VerificationInput) -> VerificationResult:
        identity = {
            "puzzle_artifact_id": value.puzzle_artifact_id,
            "solution_id": value.solution_id,
            "verifier_implementation": "fixture-verifier",
            "verifier_revision": "fixture-verifier-rev",
            "verifier_sha256": "c" * 64,
            "validation_profile": value.validation_profile,
        }
        return VerificationResult(
            verification_id=verification_id(**identity),
            **identity,
            parse_status="passed",
            simulation_status="passed",
            cost=20,
            cycles=40,
            area=10,
            instructions=6,
            vanilla_constructible=None,
            record_eligible=None,
            error_code=None,
            error_detail=None,
        )


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


def _solution_bytes() -> bytes:
    # Minimal valid format-7 unsolved solution with no parts.
    return (
        struct.pack("<I", 7)
        + b"\x04P001"
        + b"\x07fixture"
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
    )


def test_landed_verification_and_normalization_outputs_feed_release_projection(
    tmp_path: Path,
):
    store = ContentStore(tmp_path / "cache")
    puzzle_object = store.put_bytes(b"puzzle-bytes")
    solution_object = store.put_bytes(_solution_bytes())
    puzzle = ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id=f"om.puzzle-artifact.sha256.{puzzle_object.sha256}",
        puzzle_id="om.puzzle.0001",
        sha256=puzzle_object.sha256,
        byte_length=puzzle_object.byte_length,
        artifact_format="puzzle",
        rights_status="local_fetch_only",
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
    puzzle_provenance = ArtifactProvenance(
        artifact_id=puzzle.artifact_id,
        puzzle_id=puzzle.puzzle_id,
        source_role="artifact",
        source_id="fixture-puzzles",
        source_revision="fixture-puzzles-rev",
        source_path="P007.puzzle",
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
    observation_body = {
        "artifact_kind": "solution",
        "artifact_id": solution.artifact_id,
        "puzzle_id": solution.puzzle_id,
        "source_role": "artifact",
        "source_id": "fixture-solutions",
        "source_revision": "fixture-solutions-rev",
        "source_object_id": None,
        "source_path": "P007/fixture.solution",
        "associated_artifact_path": None,
        "source_declared_puzzle_id": None,
        "source_url": None,
        "author": None,
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
    observation_digest = sha256_bytes(canonical_json_bytes(observation_body))
    solution_observation = Observation(
        observation_id=f"om.observation.sha256.{observation_digest}",
        **observation_body,
    )

    verifications = materialize_verifications(
        (puzzle, solution),
        store=store,
        verifier=_FixtureVerifier(),
        validation_profile="omsim-libverify-v1",
    )
    normalized = normalize_solution_artifacts(
        (solution,),
        store,
        OpusSolutionNormalizer(),
    )

    records = materialize_release_records(
        _collection(),
        puzzle_artifacts=(puzzle,),
        puzzle_provenance=(puzzle_provenance,),
        solution_artifacts=(solution,),
        observations=(solution_observation,),
        verifications=verifications,
        normalized_solutions=normalized,
    )

    solution_row = records["solutions"][0]
    assert solution_row["verified"] is True
    assert solution_row["cost"] == 20
    assert "claimed_cost" not in solution_row
    assert solution_row["normalized_solution_id"] == normalized[0]["normalized_solution_id"]
    solution_observations = [
        row for row in records["observations"] if row["artifact_kind"] == "solution"
    ]
    assert solution_observations[0]["claimed_cost"] == 999
