from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.puzzle_definition import (
    PuzzleDefinitionConflictError,
    PuzzleDefinitionEvidence,
)
from opus_corpus.puzzle_facts import materialize_puzzle_definitions
from opus_corpus.puzzle_materialization import derive_puzzle_coverage


def _collection() -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture",
        inventory_sha256="a" * 64,
        puzzle_count=1,
        manifest_path=Path("collection.toml"),
        inventory_path=Path("collection.csv"),
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0001",
                "display_name": "Alpha Puzzle",
                "kind": "campaign",
                "group": "chapter-1",
                "game_puzzle_id": "P001",
                "leaderboard_key": "ALPHA_PUZZLE",
                "puzzle_type": "normal",
            },
        ),
        manifest={},
    )


def _semantics(*, atom_type: str = "salt") -> dict[str, object]:
    molecule = {
        "atoms": [{"atom_type": atom_type, "q": 0, "r": 0}],
        "bonds": [],
    }
    return {
        "allowed_parts": ["arm1", "bonder"],
        "allowed_instructions": ["grab", "drop"],
        "reagents": [molecule],
        "products": [molecule],
        "output_scale": 1,
        "target_output_count": 6,
        "production": False,
        "production_constraints": None,
    }


def test_complete_semantics_materialize_without_binary_artifact() -> None:
    evidence = PuzzleDefinitionEvidence(
        puzzle_id="om.puzzle.0001",
        observation_ids=("semantic-observation",),
        claims=_semantics(),
    )

    result = materialize_puzzle_definitions(_collection(), (evidence,))

    assert len(result.definitions) == 1
    definition = result.definitions[0]
    assert definition["puzzle_id"] == "om.puzzle.0001"
    assert definition["puzzle_artifact_ids"] == []
    assert definition["source_observation_ids"] == ["semantic-observation"]
    assert result.resolutions[0].missing_fields == ()


def test_equivalent_exact_artifacts_reconcile_to_one_semantic_definition() -> None:
    first_artifact = "om.puzzle-artifact.sha256." + "1" * 64
    second_artifact = "om.puzzle-artifact.sha256." + "2" * 64
    evidence = (
        PuzzleDefinitionEvidence(
            puzzle_id="om.puzzle.0001",
            observation_ids=("obs-a",),
            puzzle_artifact_ids=(first_artifact,),
            claims=_semantics(),
        ),
        PuzzleDefinitionEvidence(
            puzzle_id="om.puzzle.0001",
            observation_ids=("obs-b",),
            puzzle_artifact_ids=(second_artifact,),
            claims=_semantics(),
        ),
    )

    result = materialize_puzzle_definitions(_collection(), evidence)

    assert len(result.definitions) == 1
    definition = result.definitions[0]
    assert definition["puzzle_artifact_ids"] == [first_artifact, second_artifact]
    assert definition["source_observation_ids"] == ["obs-a", "obs-b"]


def test_conflicting_semantics_fail_closed() -> None:
    evidence = (
        PuzzleDefinitionEvidence(
            puzzle_id="om.puzzle.0001",
            observation_ids=("obs-a",),
            claims=_semantics(atom_type="salt"),
        ),
        PuzzleDefinitionEvidence(
            puzzle_id="om.puzzle.0001",
            observation_ids=("obs-b",),
            claims=_semantics(atom_type="air"),
        ),
    )

    with pytest.raises(PuzzleDefinitionConflictError, match="om.puzzle.0001"):
        materialize_puzzle_definitions(_collection(), evidence)


def test_coverage_keeps_semantic_artifact_and_verifier_axes_independent() -> None:
    definition = materialize_puzzle_definitions(
        _collection(),
        (
            PuzzleDefinitionEvidence(
                puzzle_id="om.puzzle.0001",
                observation_ids=("obs-a",),
                claims=_semantics(),
            ),
        ),
    ).definitions[0]

    coverage = derive_puzzle_coverage(
        _collection(),
        artifacts=(),
        provenance=(),
        definitions=(definition,),
        semantic_source_ids_by_puzzle={"om.puzzle.0001": ("molecule-db",)},
    )[0]

    assert coverage.puzzle_definition_id == definition["puzzle_definition_id"]
    assert coverage.semantic_source_ids == ("molecule-db",)
    assert coverage.semantic_covered is True
    assert coverage.artifact_covered is False
    assert coverage.verifier_ready is False
