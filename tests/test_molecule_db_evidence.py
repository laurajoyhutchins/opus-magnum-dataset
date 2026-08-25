from __future__ import annotations

import importlib
import importlib.util

import pytest

from opus_corpus.adapters.molecule_db import (
    MoleculeDbAtom,
    MoleculeDbBond,
    MoleculeDbMolecule,
    MoleculeDbMoleculeUse,
    MoleculeDbPuzzleSemantics,
)
from opus_corpus.errors import CorpusError


def _module():
    assert importlib.util.find_spec("opus_corpus.molecule_db_evidence") is not None
    return importlib.import_module("opus_corpus.molecule_db_evidence")


def _semantics(*, bond_type: str = "Normal") -> MoleculeDbPuzzleSemantics:
    molecule = MoleculeDbMolecule(
        atoms=(
            MoleculeDbAtom(q=1, r=0, atom_type="Fire"),
            MoleculeDbAtom(q=0, r=0, atom_type="Salt"),
        ),
        bonds=(
            MoleculeDbBond(
                start_q=1,
                start_r=0,
                end_q=0,
                end_r=0,
                bond_type=bond_type,
            ),
        ),
    )
    return MoleculeDbPuzzleSemantics(
        puzzle_id="om.puzzle.0001",
        game_puzzle_id="P001",
        variant="AlphaPuzzle",
        display_name="Alpha Puzzle",
        source_collection="Campaign(1)",
        molecule_uses=(
            MoleculeDbMoleculeUse(
                molecule=molecule,
                reagent_count=2,
                product_count=1,
                name="Alpha Molecule",
            ),
        ),
    )


def test_molecule_db_claims_only_topology_and_multiplicity() -> None:
    module = _module()
    claims = module.molecule_db_semantic_claims(_semantics())

    assert set(claims) == {"reagents", "products"}
    assert len(claims["reagents"]) == 2
    assert len(claims["products"]) == 1
    molecule = claims["reagents"][0]
    assert molecule["atoms"] == [
        {"atom_type": "fire", "q": 1, "r": 0},
        {"atom_type": "salt", "q": 0, "r": 0},
    ]
    assert molecule["bonds"] == [
        {
            "a_q": 1,
            "a_r": 0,
            "b_q": 0,
            "b_r": 0,
            "bond_types": ["normal"],
        }
    ]
    assert "allowed_parts" not in claims
    assert "allowed_instructions" not in claims
    assert "output_scale" not in claims
    assert "production" not in claims


def test_molecule_db_triplex_bond_maps_to_explicit_semantic_components() -> None:
    module = _module()
    claims = module.molecule_db_semantic_claims(
        _semantics(bond_type="Triplex { red: true, black: false, yellow: true }")
    )
    assert claims["reagents"][0]["bonds"][0]["bond_types"] == [
        "triplex-red",
        "triplex-yellow",
    ]


def test_molecule_db_unknown_bond_type_fails_closed() -> None:
    module = _module()
    with pytest.raises(CorpusError, match="bond type"):
        module.molecule_db_semantic_claims(_semantics(bond_type="FutureBond"))
