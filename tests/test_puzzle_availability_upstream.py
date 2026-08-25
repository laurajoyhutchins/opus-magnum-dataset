from __future__ import annotations

import re

import pytest

from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.errors import CorpusError
from opus_corpus.github_source import iter_github_tarball_members
from opus_corpus.puzzle_decoder import decode_puzzle_definition_evidence
from opus_corpus.puzzle_parser import ParsedPuzzle, ParsedPuzzleAtom, ParsedPuzzleMolecule

_OPCODE_NAMES = {
    "R": "rotate_cw",
    "r": "rotate_ccw",
    "E": "extend",
    "e": "retract",
    "G": "grab",
    "g": "drop",
    "P": "pivot_cw",
    "p": "pivot_ccw",
    "A": "track_plus",
    "a": "track_minus",
    "C": "repeat",
    "X": "reset",
    "B": "halt",
    "O": "noop",
}


def _decode_source() -> str:
    for path, member in iter_github_tarball_members(
        "ianh", "omsim", OmsimAdapter.pinned_revision
    ):
        if path == "decode.c":
            return member.read().decode("utf-8")
    raise AssertionError("pinned omsim tarball is missing decode.c")


def _part_requirements(source: str) -> dict[str, int]:
    return {
        name: 1 << int(bit)
        for name, bit in re.findall(
            r'byte_string_is\(part_name, "([^"]+)"\)\)\s*return 1ull << (\d+);',
            source,
        )
    }


def _instruction_requirements(source: str) -> dict[str, int]:
    match = re.search(
        r"static uint64_t\s+parts_available_bits_for_instruction\(char\s+\w+\)\s*"
        r"\{(?P<body>.*?)\n\}",
        source,
        re.DOTALL,
    )
    assert match is not None
    return {
        opcode: 1 << int(bit)
        for opcode, bit in re.findall(
            r"case '(.)':\s*return 1ull << (\d+);",
            match.group("body"),
        )
    }


def _parsed(mask: int) -> ParsedPuzzle:
    reagent = ParsedPuzzleMolecule(
        atoms=(ParsedPuzzleAtom(atom_type=1, q=0, r=0),),
        bonds=(),
    )
    product = ParsedPuzzleMolecule(
        atoms=(ParsedPuzzleAtom(atom_type=2, q=0, r=0),),
        bonds=(),
    )
    return ParsedPuzzle(
        format_version=3,
        name=b"availability-contract",
        creator=0,
        parts_available=mask,
        inputs=(reagent,),
        outputs=(product,),
        output_scale=1,
        production_info=None,
    )


def _decode(mask: int):
    return decode_puzzle_definition_evidence(
        _parsed(mask),
        puzzle_id="om.puzzle.upstream-availability",
        observation_ids=("om.observation.upstream-availability",),
        puzzle_artifact_id="om.puzzle-artifact.upstream-availability",
    )


@pytest.mark.upstream
def test_complete_availability_vocabulary_matches_pinned_omsim() -> None:
    source = _decode_source()
    part_requirements = _part_requirements(source)
    instruction_requirements = _instruction_requirements(source)
    assert part_requirements
    assert set(instruction_requirements) == set(_OPCODE_NAMES) - {"B"}

    known_mask = 0
    for required in (*part_requirements.values(), *instruction_requirements.values()):
        known_mask |= required

    for bit in range(64):
        mask = 1 << bit
        if not known_mask & mask:
            with pytest.raises(CorpusError, match="unknown.*availability.*bit"):
                _decode(mask)
            continue

        evidence = _decode(mask)
        expected_parts = sorted(
            name
            for name, required in part_requirements.items()
            if mask & required == required
        )
        expected_instructions = sorted(
            name
            for opcode, name in _OPCODE_NAMES.items()
            if opcode == "B"
            or mask & instruction_requirements[opcode]
            == instruction_requirements[opcode]
        )
        assert evidence.claims["allowed_parts"] == expected_parts
        assert evidence.claims["allowed_instructions"] == expected_instructions

    all_evidence = _decode(known_mask)
    assert all_evidence.claims["allowed_parts"] == sorted(part_requirements)
    assert all_evidence.claims["allowed_instructions"] == sorted(_OPCODE_NAMES.values())
