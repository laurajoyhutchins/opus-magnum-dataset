from __future__ import annotations

import re
from typing import Any

from .adapters.molecule_db import MoleculeDbMolecule, MoleculeDbPuzzleSemantics
from .errors import CorpusError

_TRIPLEX_RE = re.compile(
    r"^Triplex \{ red: (?P<red>true|false), black: (?P<black>true|false), "
    r"yellow: (?P<yellow>true|false) \}$"
)


class MoleculeDbEvidenceError(CorpusError):
    """Raised when molecule-db semantics cannot be mapped canonically."""


def _bond_types(value: str) -> list[str]:
    if value == "Normal":
        return ["normal"]
    match = _TRIPLEX_RE.fullmatch(value)
    if match is None:
        raise MoleculeDbEvidenceError(f"unsupported molecule-db bond type {value!r}")
    result: list[str] = []
    for source_name, semantic_name in (
        ("red", "triplex-red"),
        ("black", "triplex-black"),
        ("yellow", "triplex-yellow"),
    ):
        if match.group(source_name) == "true":
            result.append(semantic_name)
    if not result:
        raise MoleculeDbEvidenceError("molecule-db triplex bond type has no active component")
    return result


def _molecule(value: MoleculeDbMolecule) -> dict[str, Any]:
    return {
        "atoms": [
            {"atom_type": atom.atom_type.lower(), "q": atom.q, "r": atom.r}
            for atom in value.atoms
        ],
        "bonds": [
            {
                "a_q": bond.start_q,
                "a_r": bond.start_r,
                "b_q": bond.end_q,
                "b_r": bond.end_r,
                "bond_types": _bond_types(bond.bond_type),
            }
            for bond in value.bonds
        ],
    }


def molecule_db_semantic_claims(value: MoleculeDbPuzzleSemantics) -> dict[str, Any]:
    """Translate only semantic topology facts explicitly present in molecule-db."""

    reagents: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    for use in value.molecule_uses:
        reagents.extend(_molecule(use.molecule) for _ in range(use.reagent_count))
        products.extend(_molecule(use.molecule) for _ in range(use.product_count))

    if not reagents:
        raise MoleculeDbEvidenceError(
            f"{value.puzzle_id}: molecule-db supplies no reagent topology"
        )
    if not products:
        raise MoleculeDbEvidenceError(
            f"{value.puzzle_id}: molecule-db supplies no product topology"
        )
    return {"reagents": reagents, "products": products}
