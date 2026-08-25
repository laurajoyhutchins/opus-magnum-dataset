from __future__ import annotations

import importlib
import importlib.util

import pytest


def _module():
    assert importlib.util.find_spec("opus_corpus.puzzle_definition") is not None
    return importlib.import_module("opus_corpus.puzzle_definition")


def _molecule(*, reverse: bool = False, atom_type: str = "air") -> dict[str, object]:
    atoms = [
        {"atom_type": "salt", "q": 0, "r": 0},
        {"atom_type": atom_type, "q": 1, "r": 0},
    ]
    if reverse:
        atoms.reverse()
    bond = {
        "a_q": 0,
        "a_r": 0,
        "b_q": 1,
        "b_r": 0,
        "bond_types": ["normal"],
    }
    if reverse:
        bond = {
            "a_q": 1,
            "a_r": 0,
            "b_q": 0,
            "b_r": 0,
            "bond_types": ["normal"],
        }
    return {"atoms": atoms, "bonds": [bond]}


def _semantics(*, reverse: bool = False) -> dict[str, object]:
    reagent = _molecule(reverse=reverse)
    return {
        "allowed_parts": ["bonder", "arm1"] if not reverse else ["arm1", "bonder"],
        "allowed_instructions": ["rotate", "grab"] if not reverse else ["grab", "rotate"],
        "reagents": [reagent, reagent],
        "products": [_molecule(reverse=reverse, atom_type="fire")],
        "output_scale": 1,
        "target_output_count": 6,
        "production": False,
        "production_constraints": None,
    }


def test_semantic_identity_ignores_artifact_and_provenance_order() -> None:
    module = _module()
    first = module.build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics=_semantics(),
        source_observation_ids=["obs-b", "obs-a"],
        puzzle_artifact_ids=["om.puzzle-artifact.sha256." + "2" * 64],
    )
    second = module.build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics=_semantics(reverse=True),
        source_observation_ids=["obs-z"],
        puzzle_artifact_ids=["om.puzzle-artifact.sha256." + "3" * 64],
    )

    assert first["puzzle_definition_id"] == second["puzzle_definition_id"]
    assert first["reagents"] == second["reagents"]
    assert first["allowed_parts"] == ["arm1", "bonder"]
    assert first["source_observation_ids"] == ["obs-a", "obs-b"]


def test_canonicalization_preserves_repeated_molecule_multiplicity() -> None:
    module = _module()
    definition = module.build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics=_semantics(),
    )
    assert len(definition["reagents"]) == 2
    assert definition["reagents"][0] == definition["reagents"][1]


def test_definition_validates_without_an_exact_artifact() -> None:
    module = _module()
    definition = module.build_puzzle_definition(
        puzzle_id="om.puzzle.0001",
        semantics=_semantics(),
        source_observation_ids=["obs-a"],
        puzzle_artifact_ids=[],
    )
    module.validate_puzzle_definition(definition)
    assert definition["puzzle_artifact_ids"] == []


def test_invalid_bond_endpoint_fails_closed() -> None:
    module = _module()
    semantics = _semantics()
    semantics["products"] = [
        {
            "atoms": [{"atom_type": "salt", "q": 0, "r": 0}],
            "bonds": [
                {
                    "a_q": 0,
                    "a_r": 0,
                    "b_q": 9,
                    "b_r": 9,
                    "bond_types": ["normal"],
                }
            ],
        }
    ]
    with pytest.raises(module.PuzzleDefinitionError, match="bond endpoint"):
        module.build_puzzle_definition(
            puzzle_id="om.puzzle.0001",
            semantics=semantics,
        )


def test_reconciliation_merges_partial_evidence_deterministically() -> None:
    module = _module()
    semantics = _semantics()
    evidence = [
        module.PuzzleDefinitionEvidence(
            puzzle_id="om.puzzle.0001",
            observation_id="obs-b",
            claims={
                "allowed_parts": semantics["allowed_parts"],
                "allowed_instructions": semantics["allowed_instructions"],
            },
        ),
        module.PuzzleDefinitionEvidence(
            puzzle_id="om.puzzle.0001",
            observation_id="obs-a",
            claims={
                key: value
                for key, value in semantics.items()
                if key not in {"allowed_parts", "allowed_instructions"}
            },
        ),
    ]

    first = module.reconcile_puzzle_definition("om.puzzle.0001", evidence)
    second = module.reconcile_puzzle_definition("om.puzzle.0001", reversed(evidence))
    assert first.definition == second.definition
    assert first.missing_fields == ()
    assert first.definition["source_observation_ids"] == ["obs-a", "obs-b"]


def test_incomplete_evidence_remains_explicitly_unresolved() -> None:
    module = _module()
    resolution = module.reconcile_puzzle_definition(
        "om.puzzle.0001",
        [
            module.PuzzleDefinitionEvidence(
                puzzle_id="om.puzzle.0001",
                observation_id="obs-a",
                claims={"reagents": _semantics()["reagents"]},
            )
        ],
    )
    assert resolution.definition is None
    assert "allowed_parts" in resolution.missing_fields
    assert "production" in resolution.missing_fields


def test_conflicting_semantic_evidence_fails_closed_with_field_context() -> None:
    module = _module()
    first = module.PuzzleDefinitionEvidence(
        puzzle_id="om.puzzle.0001",
        observation_id="obs-a",
        claims={"reagents": [_molecule()]},
    )
    second = module.PuzzleDefinitionEvidence(
        puzzle_id="om.puzzle.0001",
        observation_id="obs-b",
        claims={"reagents": [_molecule(atom_type="fire")]},
    )
    with pytest.raises(module.PuzzleDefinitionConflictError) as caught:
        module.reconcile_puzzle_definition("om.puzzle.0001", [first, second])
    message = str(caught.value)
    assert "om.puzzle.0001" in message
    assert "reagents" in message
    assert "obs-a" in message
    assert "obs-b" in message


def test_output_target_must_match_scale() -> None:
    module = _module()
    semantics = _semantics()
    semantics["output_scale"] = 2
    with pytest.raises(module.PuzzleDefinitionError, match="target_output_count"):
        module.build_puzzle_definition(
            puzzle_id="om.puzzle.0001",
            semantics=semantics,
        )
