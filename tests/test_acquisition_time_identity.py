"""Acquisition clocks are audit metadata, never canonical corpus identities."""
from __future__ import annotations

from dataclasses import asdict, replace

from jsonschema import Draft202012Validator

from opus_corpus.hashing import canonical_json_bytes
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.observations import observation_id
from opus_corpus.puzzle_definition import build_puzzle_definition
from opus_corpus.puzzle_materialization import materialize_puzzle_provenance_observations
from opus_corpus.schema_resources import load_schema_resource
from opus_corpus.solution_materialization import _observation_from_provenance


def _provenance(artifact: ArtifactRecord, retrieved_at: str) -> ArtifactProvenance:
    return ArtifactProvenance(
        artifact_id=artifact.artifact_id,
        puzzle_id=artifact.puzzle_id,
        source_role="artifact",
        source_id="omsim",
        source_revision="pinned-revision",
        source_path="campaign/P001.puzzle",
        source_object_id="P001",
        source_url=None,
        author=None,
        retrieved_at=retrieved_at,
        rights_status="local_fetch_only",
        observed_sha256=artifact.sha256,
        source_evidence_sha256=artifact.sha256,
        source_evidence_byte_length=artifact.byte_length,
        claimed_cost=None,
        claimed_cycles=None,
        claimed_area=None,
        claimed_instructions=None,
    )


def _artifact(kind: str) -> ArtifactRecord:
    digest = "a" * 64
    return ArtifactRecord(
        artifact_kind=kind,
        artifact_id=f"om.{kind}.sha256.{digest}",
        puzzle_id="om.puzzle.0001",
        sha256=digest,
        byte_length=42,
        artifact_format=kind,
        rights_status="local_fetch_only",
        object_key=f"objects/sha256/{digest[:2]}/{digest[2:]}",
    )


def _semantic_definition(source_observation_id: str) -> dict[str, object]:
    molecule = {"atoms": [{"atom_type": "salt", "q": 0, "r": 0}], "bonds": []}
    return build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
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
        source_observation_ids=[source_observation_id],
        puzzle_artifact_ids=[],
    )


def test_puzzle_observation_semantics_and_release_bytes_ignore_fetch_clock() -> None:
    artifact = _artifact("puzzle")
    first = _provenance(artifact, "2026-08-24T01:00:00Z")
    second = replace(first, retrieved_at="2027-12-31T23:59:59Z")

    row1 = materialize_puzzle_provenance_observations([artifact], [first])[0]
    row2 = materialize_puzzle_provenance_observations([artifact], [second])[0]
    assert row1 == row2
    assert "retrieved_at" not in row1
    assert row1["source_revision"] == "pinned-revision"
    assert row1["source_evidence_sha256"] == artifact.sha256
    assert row1["observed_sha256"] == artifact.sha256

    definition1 = _semantic_definition(row1["observation_id"])
    definition2 = _semantic_definition(row2["observation_id"])
    assert canonical_json_bytes(definition1) == canonical_json_bytes(definition2)
    assert canonical_json_bytes({"observations": [row1], "definitions": [definition1]}) == (
        canonical_json_bytes({"observations": [row2], "definitions": [definition2]})
    )


def test_solution_observation_identity_and_bytes_ignore_fetch_clock() -> None:
    artifact = _artifact("solution")
    first = _provenance(artifact, "2026-08-24T01:00:00Z")
    second = replace(first, retrieved_at="2035-01-01T00:00:00Z")
    row1 = asdict(_observation_from_provenance(first, {}))
    row2 = asdict(_observation_from_provenance(second, {}))

    assert row1 == row2
    assert "retrieved_at" not in row1
    assert row1["source_revision"] == "pinned-revision"
    assert row1["source_evidence_sha256"] == artifact.sha256
    assert canonical_json_bytes(row1) == canonical_json_bytes(row2)


def test_clock_bearing_legacy_rows_must_rebuild_under_new_schema() -> None:
    artifact = _artifact("puzzle")
    provenance = _provenance(artifact, "2026-08-24T01:00:00Z")
    row = materialize_puzzle_provenance_observations([artifact], [provenance])[0]
    validator = Draft202012Validator(load_schema_resource("observation.schema.json").schema)
    assert not list(validator.iter_errors(row))

    old_body = {key: value for key, value in row.items() if key != "observation_id"}
    old_body["retrieved_at"] = provenance.retrieved_at
    legacy_id = observation_id(old_body)
    assert legacy_id != row["observation_id"]
    legacy_row = {"observation_id": legacy_id, **old_body}
    assert list(validator.iter_errors(legacy_row)), "old canonical observation must not be admitted"
