from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from opus_corpus.benchmark_eligibility import (
    ELIGIBILITY_PROFILE,
    ELIGIBILITY_VERSION,
    BenchmarkEligibilityError,
    benchmark_eligibility_bytes,
    derive_benchmark_eligibility,
)
from opus_corpus.collections import CollectionDefinition
from opus_corpus.ingestion import ArtifactProvenance, ArtifactRecord
from opus_corpus.puzzle_definition import build_puzzle_definition


def collection(*puzzle_types: str) -> CollectionDefinition:
    rows = tuple(
        {
            "puzzle_id": f"om.puzzle.{index:04d}",
            "display_name": f"Puzzle {index}",
            "kind": "campaign",
            "group": "fixture",
            "game_puzzle_id": f"P{index:03d}",
            "leaderboard_key": f"PUZZLE_{index}",
            "puzzle_type": puzzle_type,
        }
        for index, puzzle_type in enumerate(puzzle_types, start=1)
    )
    return CollectionDefinition(
        collection_id="fixture-v1",
        inventory_sha256="a" * 64,
        puzzle_count=len(rows),
        manifest_path=Path("fixture.toml"),
        inventory_path=Path("fixture.csv"),
        inventory_rows=rows,
        manifest={},
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


def artifact(puzzle_id: str, digit: str, *, artifact_format: str = "puzzle") -> ArtifactRecord:
    digest = digit * 64
    return ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id=f"om.puzzle-artifact.sha256.{digest}",
        puzzle_id=puzzle_id,
        sha256=digest,
        byte_length=123,
        artifact_format=artifact_format,
        rights_status="local_fetch_only",
        object_key=f"objects/sha256/{digest[:2]}/{digest}",
    )


def provenance(record: ArtifactRecord, source_id: str) -> ArtifactProvenance:
    return ArtifactProvenance(
        artifact_id=record.artifact_id,
        puzzle_id=record.puzzle_id,
        source_role="artifact",
        source_id=source_id,
        source_revision="rev-a",
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


def test_projection_distinguishes_semantic_artifact_and_verifier_ready_coverage() -> None:
    value = collection("normal", "normal", "normal", "normal")
    puzzle_ids = [row["puzzle_id"] for row in value.inventory_rows]
    missing_semantic_artifact = artifact(puzzle_ids[0], "1")
    unusable_artifact = artifact(puzzle_ids[2], "2", artifact_format="unsupported")
    executable_artifact = artifact(puzzle_ids[3], "3")

    result = derive_benchmark_eligibility(
        value,
        definitions=[definition(puzzle_id) for puzzle_id in puzzle_ids[1:]],
        artifacts=[missing_semantic_artifact, unusable_artifact, executable_artifact],
        provenance=[
            provenance(missing_semantic_artifact, "omsim"),
            provenance(unusable_artifact, "omsim"),
            provenance(executable_artifact, "omsim"),
        ],
    )

    assert result.profile == ELIGIBILITY_PROFILE
    assert result.version == ELIGIBILITY_VERSION
    rows = {row.puzzle_id: row for row in result.entries}

    assert rows[puzzle_ids[0]].semantic_covered is False
    assert rows[puzzle_ids[0]].artifact_covered is True
    assert rows[puzzle_ids[0]].verifier_ready is True
    assert rows[puzzle_ids[0]].eligible is False
    assert rows[puzzle_ids[0]].exclusion_reason == "missing_semantic_definition"

    assert rows[puzzle_ids[1]].semantic_covered is True
    assert rows[puzzle_ids[1]].artifact_covered is False
    assert rows[puzzle_ids[1]].verifier_ready is False
    assert rows[puzzle_ids[1]].exclusion_reason == "missing_exact_artifact"

    assert rows[puzzle_ids[2]].semantic_covered is True
    assert rows[puzzle_ids[2]].artifact_covered is True
    assert rows[puzzle_ids[2]].verifier_ready is False
    assert rows[puzzle_ids[2]].exclusion_reason == "no_verifier_usable_artifact"

    executable = rows[puzzle_ids[3]]
    assert executable.semantic_covered is True
    assert executable.artifact_covered is True
    assert executable.verifier_ready is True
    assert executable.eligible is True
    assert executable.exclusion_reason is None
    assert executable.selected_puzzle_artifact_id == executable_artifact.artifact_id
    assert executable.selected_puzzle_artifact_sha256 == executable_artifact.sha256
    assert executable.selected_source_ids == ("omsim",)
    assert result.executable_entries == (executable,)


def test_projection_is_byte_identical_under_all_input_orderings_and_prefers_official_bytes() -> None:
    value = collection("normal")
    puzzle_id = value.inventory_rows[0]["puzzle_id"]
    semantic = definition(puzzle_id)
    omsim_artifact = artifact(puzzle_id, "4")
    official_artifact = artifact(puzzle_id, "5")
    rows = [provenance(omsim_artifact, "omsim"), provenance(official_artifact, "official-game")]

    first = derive_benchmark_eligibility(
        value,
        definitions=[semantic],
        artifacts=[omsim_artifact, official_artifact],
        provenance=rows,
    )
    second = derive_benchmark_eligibility(
        value,
        definitions=[semantic],
        artifacts=[official_artifact, omsim_artifact],
        provenance=list(reversed(rows)),
    )

    assert benchmark_eligibility_bytes(first) == benchmark_eligibility_bytes(second)
    assert first.inventory_id == second.inventory_id
    selected = first.executable_entries[0]
    assert selected.selected_puzzle_artifact_id == official_artifact.artifact_id
    assert selected.selected_source_ids == ("official-game",)


def test_inventory_identity_changes_when_membership_or_selected_artifact_changes() -> None:
    value = collection("normal", "normal")
    puzzle_a, puzzle_b = [row["puzzle_id"] for row in value.inventory_rows]
    first_a = artifact(puzzle_a, "6")
    second_a = artifact(puzzle_a, "7")
    artifact_b = artifact(puzzle_b, "8")
    definitions = [definition(puzzle_a), definition(puzzle_b)]

    only_first = derive_benchmark_eligibility(
        value,
        definitions=definitions,
        artifacts=[first_a, artifact_b],
        provenance=[provenance(first_a, "omsim"), provenance(artifact_b, "omsim")],
    )
    different_selection = derive_benchmark_eligibility(
        value,
        definitions=definitions,
        artifacts=[first_a, second_a, artifact_b],
        provenance=[
            provenance(first_a, "omsim"),
            provenance(second_a, "official-game"),
            provenance(artifact_b, "omsim"),
        ],
    )
    missing_member = derive_benchmark_eligibility(
        value,
        definitions=definitions,
        artifacts=[first_a],
        provenance=[provenance(first_a, "omsim")],
    )

    assert only_first.inventory_sha256 != different_selection.inventory_sha256
    assert only_first.inventory_sha256 != missing_member.inventory_sha256
    assert only_first.inventory_id != different_selection.inventory_id
    assert only_first.inventory_id != missing_member.inventory_id


def test_protocol_incompatibility_is_an_explicit_exclusion_reason() -> None:
    value = collection("future-puzzle-type")
    puzzle_id = value.inventory_rows[0]["puzzle_id"]
    exact = artifact(puzzle_id, "9")

    result = derive_benchmark_eligibility(
        value,
        definitions=[definition(puzzle_id)],
        artifacts=[exact],
        provenance=[provenance(exact, "official-game")],
    )

    row = result.entries[0]
    assert row.semantic_covered is True
    assert row.artifact_covered is True
    assert row.verifier_ready is True
    assert row.eligible is False
    assert row.exclusion_reason == "protocol_incompatible"


def test_duplicate_or_conflicting_canonical_inputs_fail_closed() -> None:
    value = collection("normal")
    puzzle_id = value.inventory_rows[0]["puzzle_id"]
    semantic = definition(puzzle_id)
    exact = artifact(puzzle_id, "a")
    source = provenance(exact, "omsim")

    with pytest.raises(BenchmarkEligibilityError, match="duplicate puzzle definition"):
        derive_benchmark_eligibility(
            value,
            definitions=[semantic, dict(semantic)],
            artifacts=[exact],
            provenance=[source],
        )

    with pytest.raises(BenchmarkEligibilityError, match="duplicate puzzle artifact"):
        derive_benchmark_eligibility(
            value,
            definitions=[semantic],
            artifacts=[exact, replace(exact)],
            provenance=[source],
        )

    conflicting = replace(source, observed_sha256="b" * 64)
    with pytest.raises(BenchmarkEligibilityError, match="provenance hash"):
        derive_benchmark_eligibility(
            value,
            definitions=[semantic],
            artifacts=[exact],
            provenance=[conflicting],
        )