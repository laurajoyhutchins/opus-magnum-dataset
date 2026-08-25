from __future__ import annotations

from typing import Any

from .errors import CorpusError
from .puzzle_definition import PuzzleDefinitionEvidence
from .puzzle_parser import ParsedPuzzle, ParsedPuzzleMolecule, ParsedPuzzleProductionInfo


class PuzzleDecodeError(CorpusError):
    """Raised when parsed puzzle structure cannot be mapped to canonical semantics."""


_ATOM_TYPES = {
    1: "salt",
    2: "air",
    3: "earth",
    4: "fire",
    5: "water",
    6: "quicksilver",
    7: "gold",
    8: "silver",
    9: "copper",
    10: "iron",
    11: "tin",
    12: "lead",
    13: "vitae",
    14: "mors",
    15: "repeat",
    16: "quintessence",
    17: "variable",
}

_BOND_BITS = (
    (1, "normal"),
    (2, "triplex-red"),
    (4, "triplex-black"),
    (8, "triplex-yellow"),
)
_BOND_MASK = sum(bit for bit, _ in _BOND_BITS)

_PART_REQUIREMENTS = {
    "arm1": 1 << 0,
    "arm2": 1 << 1,
    "arm3": 1 << 1,
    "arm6": 1 << 1,
    "baron": 1 << 28,
    "bonder": 1 << 8,
    "bonder-prisma": 1 << 11,
    "bonder-speed": 1 << 10,
    "glyph-calcification": 1 << 12,
    "glyph-dispersion": 1 << 18,
    "glyph-disposal": 1 << 17,
    "glyph-division": 1 << 20,
    "glyph-duplication": 1 << 13,
    "glyph-life-and-death": 1 << 16,
    "glyph-marker": 1 << 1,
    "glyph-projection": 1 << 14,
    "glyph-proliferation": 1 << 21,
    "glyph-purification": 1 << 15,
    "glyph-rejection": 1 << 19,
    "glyph-unification": 1 << 18,
    "piston": 1 << 2,
    "ravari": 1 << 29,
    "track": 1 << 3,
    "unbonder": 1 << 9,
}

_INSTRUCTION_REQUIREMENTS = {
    "drop": 1 << 22,
    "extend": 1 << 2,
    "grab": 1 << 23,
    "halt": 0,
    "noop": 1 << 25,
    "pivot_ccw": 1 << 26,
    "pivot_cw": 1 << 26,
    "repeat": 1 << 25,
    "reset": 1 << 24,
    "retract": 1 << 2,
    "rotate_ccw": 1 << 22,
    "rotate_cw": 1 << 22,
    "track_minus": 1 << 3,
    "track_plus": 1 << 3,
}

_KNOWN_AVAILABILITY_MASK = 0
for _mask in (*_PART_REQUIREMENTS.values(), *_INSTRUCTION_REQUIREMENTS.values()):
    _KNOWN_AVAILABILITY_MASK |= _mask


def _availability(mask: int) -> tuple[list[str], list[str]]:
    unknown = mask & ~_KNOWN_AVAILABILITY_MASK
    if unknown:
        bit_numbers = [str(bit) for bit in range(64) if unknown & (1 << bit)]
        raise PuzzleDecodeError(
            "unknown puzzle availability bit(s): " + ", ".join(bit_numbers)
        )
    parts = sorted(
        name for name, required in _PART_REQUIREMENTS.items() if mask & required == required
    )
    instructions = sorted(
        name
        for name, required in _INSTRUCTION_REQUIREMENTS.items()
        if mask & required == required
    )
    return parts, instructions


def _atom_type(value: int) -> str:
    try:
        return _ATOM_TYPES[value]
    except KeyError as exc:
        raise PuzzleDecodeError(f"unknown atom type {value}") from exc


def _bond_types(value: int) -> list[str]:
    if value == 0 or value & ~_BOND_MASK:
        raise PuzzleDecodeError(f"invalid puzzle bond type {value}")
    return [name for bit, name in _BOND_BITS if value & bit]


def _molecule(value: ParsedPuzzleMolecule) -> dict[str, Any]:
    if not value.atoms:
        raise PuzzleDecodeError("puzzle molecule contains no atoms")
    return {
        "atoms": [
            {"atom_type": _atom_type(atom.atom_type), "q": atom.q, "r": atom.r}
            for atom in value.atoms
        ],
        "bonds": [
            {
                "a_q": bond.a_q,
                "a_r": bond.a_r,
                "b_q": bond.b_q,
                "b_r": bond.b_r,
                "bond_types": _bond_types(bond.bond_type),
            }
            for bond in value.bonds
        ],
    }


def _utf8(value: bytes, *, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PuzzleDecodeError(f"{label} is not valid UTF-8") from exc


def _production_constraints(value: ParsedPuzzleProductionInfo) -> dict[str, Any]:
    return {
        "shrink_left": value.shrink_left,
        "shrink_right": value.shrink_right,
        "isolate_inputs_from_outputs": value.isolate_inputs_from_outputs,
        "cabinets": [
            {
                "q": cabinet.q,
                "r": cabinet.r,
                "cabinet_type": _utf8(cabinet.cabinet_type, label="cabinet type"),
            }
            for cabinet in value.cabinets
        ],
        "conduits": [
            {
                "a_q": conduit.a_q,
                "a_r": conduit.a_r,
                "b_q": conduit.b_q,
                "b_r": conduit.b_r,
                "hexes": [{"q": item.q, "r": item.r} for item in conduit.hexes],
            }
            for conduit in value.conduits
        ],
        "vials": [
            {
                "q": vial.q,
                "r": vial.r,
                "style": vial.style,
                "count": vial.count,
            }
            for vial in value.vials
        ],
    }


def decode_puzzle_definition_evidence(
    parsed: ParsedPuzzle,
    *,
    puzzle_id: str,
    observation_ids: tuple[str, ...],
    puzzle_artifact_id: str,
) -> PuzzleDefinitionEvidence:
    """Translate parsed format-3 structure into one complete semantic claim set."""

    if parsed.format_version != 3:
        raise PuzzleDecodeError(
            f"unsupported parsed puzzle format version {parsed.format_version}"
        )
    if parsed.output_scale < 1:
        raise PuzzleDecodeError("puzzle output_scale must be at least 1")
    if not parsed.inputs:
        raise PuzzleDecodeError("puzzle requires at least one reagent molecule")
    if not parsed.outputs:
        raise PuzzleDecodeError("puzzle requires at least one product molecule")

    allowed_parts, allowed_instructions = _availability(parsed.parts_available)
    production = parsed.production_info is not None
    claims = {
        "allowed_parts": allowed_parts,
        "allowed_instructions": allowed_instructions,
        "reagents": [_molecule(value) for value in parsed.inputs],
        "products": [_molecule(value) for value in parsed.outputs],
        "output_scale": parsed.output_scale,
        "target_output_count": 6 * parsed.output_scale,
        "production": production,
        "production_constraints": (
            _production_constraints(parsed.production_info) if production else None
        ),
    }
    return PuzzleDefinitionEvidence(
        puzzle_id=puzzle_id,
        observation_ids=observation_ids,
        claims=claims,
        puzzle_artifact_id=puzzle_artifact_id,
    )
