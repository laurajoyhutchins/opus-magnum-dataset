from __future__ import annotations

import pytest

from opus_corpus.errors import CorpusError
from opus_corpus.puzzle_definition import reconcile_puzzle_definition
from opus_corpus.puzzle_parser import (
    ParsedPuzzle,
    ParsedPuzzleAtom,
    ParsedPuzzleBond,
    ParsedPuzzleCabinet,
    ParsedPuzzleConduit,
    ParsedPuzzleConduitHex,
    ParsedPuzzleMolecule,
    ParsedPuzzleProductionInfo,
    ParsedPuzzleVial,
)


def _molecule(
    atom_type: int = 1,
    *,
    bond_type: int | None = None,
) -> ParsedPuzzleMolecule:
    atoms = [ParsedPuzzleAtom(atom_type=atom_type, q=0, r=0)]
    bonds: list[ParsedPuzzleBond] = []
    if bond_type is not None:
        atoms.append(ParsedPuzzleAtom(atom_type=4, q=1, r=0))
        bonds.append(
            ParsedPuzzleBond(
                bond_type=bond_type,
                a_q=0,
                a_r=0,
                b_q=1,
                b_r=0,
            )
        )
    return ParsedPuzzleMolecule(atoms=tuple(atoms), bonds=tuple(bonds))


def _parsed(
    *,
    parts_available: int = 0,
    atom_type: int = 1,
    bond_type: int | None = None,
    output_scale: int = 1,
    production_info: ParsedPuzzleProductionInfo | None = None,
) -> ParsedPuzzle:
    return ParsedPuzzle(
        format_version=3,
        name=b"Semantic Fixture",
        creator=0,
        parts_available=parts_available,
        inputs=(_molecule(atom_type, bond_type=bond_type),),
        outputs=(_molecule(2),),
        output_scale=output_scale,
        production_info=production_info,
    )


def _decode(parsed: ParsedPuzzle, *, artifact_suffix: str = "1"):
    from opus_corpus.puzzle_decoder import decode_puzzle_definition_evidence

    return decode_puzzle_definition_evidence(
        parsed,
        puzzle_id="om.puzzle.0001",
        observation_ids=("obs-a",),
        puzzle_artifact_id="om.puzzle-artifact.sha256." + artifact_suffix * 64,
    )


def test_decodes_pinned_availability_bits_into_parts_and_instructions() -> None:
    evidence = _decode(
        _parsed(
            parts_available=(
                (1 << 0)
                | (1 << 1)
                | (1 << 2)
                | (1 << 8)
                | (1 << 22)
                | (1 << 23)
                | (1 << 25)
                | (1 << 26)
            )
        )
    )

    assert evidence.claims["allowed_parts"] == [
        "arm1",
        "arm2",
        "arm3",
        "arm6",
        "bonder",
        "glyph-marker",
        "piston",
    ]
    assert evidence.claims["allowed_instructions"] == [
        "drop",
        "extend",
        "grab",
        "halt",
        "noop",
        "pivot_ccw",
        "pivot_cw",
        "repeat",
        "retract",
        "rotate_ccw",
        "rotate_cw",
    ]


def test_unknown_availability_bit_fails_closed() -> None:
    with pytest.raises(CorpusError, match="unknown.*availability.*bit"):
        _decode(_parsed(parts_available=1 << 63))


@pytest.mark.parametrize(
    ("atom_type", "expected"),
    [
        (1, "salt"),
        (2, "air"),
        (3, "earth"),
        (4, "fire"),
        (5, "water"),
        (6, "quicksilver"),
        (7, "gold"),
        (8, "silver"),
        (9, "copper"),
        (10, "iron"),
        (11, "tin"),
        (12, "lead"),
        (13, "vitae"),
        (14, "mors"),
        (15, "repeat"),
        (16, "quintessence"),
        (17, "variable"),
    ],
)
def test_decodes_pinned_atom_vocabulary(atom_type: int, expected: str) -> None:
    evidence = _decode(_parsed(atom_type=atom_type))
    assert evidence.claims["reagents"][0]["atoms"][0]["atom_type"] == expected


def test_unknown_atom_type_fails_closed() -> None:
    with pytest.raises(CorpusError, match="unknown atom type"):
        _decode(_parsed(atom_type=18))


def test_decodes_combined_bond_bitfield() -> None:
    evidence = _decode(_parsed(bond_type=1 | 2 | 4 | 8))
    assert evidence.claims["reagents"][0]["bonds"][0]["bond_types"] == [
        "normal",
        "triplex-red",
        "triplex-black",
        "triplex-yellow",
    ]


@pytest.mark.parametrize("bond_type", [0, 16, 255])
def test_invalid_bond_type_fails_closed(bond_type: int) -> None:
    with pytest.raises(CorpusError, match="bond type"):
        _decode(_parsed(bond_type=bond_type))


def test_derives_output_target_from_pinned_omsim_rule() -> None:
    evidence = _decode(_parsed(output_scale=7))
    assert evidence.claims["output_scale"] == 7
    assert evidence.claims["target_output_count"] == 42


def test_zero_output_scale_fails_closed() -> None:
    with pytest.raises(CorpusError, match="output_scale"):
        _decode(_parsed(output_scale=0))


def test_decodes_production_constraints_without_simulation_logic() -> None:
    info = ParsedPuzzleProductionInfo(
        shrink_left=True,
        shrink_right=False,
        isolate_inputs_from_outputs=True,
        cabinets=(ParsedPuzzleCabinet(q=-1, r=2, cabinet_type=b"SmallWide"),),
        conduits=(
            ParsedPuzzleConduit(
                a_q=1,
                a_r=2,
                b_q=-3,
                b_r=4,
                hexes=(ParsedPuzzleConduitHex(q=0, r=0),),
            ),
        ),
        vials=(ParsedPuzzleVial(q=5, r=-6, style=2, count=7),),
    )
    evidence = _decode(_parsed(production_info=info))

    assert evidence.claims["production"] is True
    assert evidence.claims["production_constraints"] == {
        "shrink_left": True,
        "shrink_right": False,
        "isolate_inputs_from_outputs": True,
        "cabinets": [{"q": -1, "r": 2, "cabinet_type": "SmallWide"}],
        "conduits": [
            {
                "a_q": 1,
                "a_r": 2,
                "b_q": -3,
                "b_r": 4,
                "hexes": [{"q": 0, "r": 0}],
            }
        ],
        "vials": [{"q": 5, "r": -6, "style": 2, "count": 7}],
    }


def test_invalid_cabinet_utf8_fails_closed() -> None:
    info = ParsedPuzzleProductionInfo(
        shrink_left=False,
        shrink_right=False,
        isolate_inputs_from_outputs=False,
        cabinets=(ParsedPuzzleCabinet(q=0, r=0, cabinet_type=b"\xff"),),
        conduits=(),
        vials=(),
    )
    with pytest.raises(CorpusError, match="cabinet type.*UTF-8"):
        _decode(_parsed(production_info=info))


def test_byte_distinct_artifacts_with_same_semantics_reconcile_to_one_definition() -> None:
    first = _decode(_parsed(), artifact_suffix="1")
    second = _decode(_parsed(), artifact_suffix="2")

    resolution = reconcile_puzzle_definition("om.puzzle.0001", [first, second])
    assert resolution.definition is not None
    assert resolution.puzzle_artifact_ids == (
        "om.puzzle-artifact.sha256." + "1" * 64,
        "om.puzzle-artifact.sha256." + "2" * 64,
    )
    assert resolution.definition["puzzle_definition_id"].startswith(
        "om.puzzle-definition.sha256."
    )


def test_artifact_semantic_disagreement_uses_shared_conflict_boundary() -> None:
    first = _decode(_parsed(atom_type=1), artifact_suffix="1")
    second = _decode(_parsed(atom_type=2), artifact_suffix="2")

    with pytest.raises(CorpusError, match="conflicting semantic evidence.*reagents"):
        reconcile_puzzle_definition("om.puzzle.0001", [first, second])
