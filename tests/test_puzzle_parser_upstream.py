from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.github_source import iter_github_tarball_members
from opus_corpus.puzzle_decoder import decode_puzzle_definition_evidence
from opus_corpus.puzzle_parser import ParsedPuzzle, parse_puzzle_bytes

_FIXTURES = (
    "test/puzzle/easy/just-salt.puzzle",
    "test/puzzle/easy/easy-conduit.puzzle",
)
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
_C_DUMPER = r'''
#include "parse.h"
#include <inttypes.h>
#include <stdio.h>

static void hex_string(struct byte_string value) {
    for (size_t i = 0; i < value.length; ++i) printf("%02x", value.bytes[i]);
}

static void molecule(const char *kind, uint32_t index, struct puzzle_molecule *value) {
    printf("%s %u %u %u\n", kind, index, value->number_of_atoms, value->number_of_bonds);
    for (uint32_t i = 0; i < value->number_of_atoms; ++i) {
        struct puzzle_atom *atom = &value->atoms[i];
        printf("a %u %u %u %d %d\n", index, i, (unsigned)atom->type,
               (int)atom->offset[0], (int)atom->offset[1]);
    }
    for (uint32_t i = 0; i < value->number_of_bonds; ++i) {
        struct puzzle_bond *bond = &value->bonds[i];
        printf("b %u %u %u %d %d %d %d\n", index, i, (unsigned)bond->type,
               (int)bond->from[0], (int)bond->from[1],
               (int)bond->to[0], (int)bond->to[1]);
    }
}

int main(int argc, char **argv) {
    if (argc != 2) return 64;
    struct puzzle_file *p = parse_puzzle_file(argv[1]);
    if (!p) return 2;
    printf("name "); hex_string(p->name); printf("\n");
    printf("header %" PRIu64 " %" PRIu64 " %u %u %u %d\n",
           p->creator, p->parts_available, p->number_of_inputs,
           p->number_of_outputs, p->output_scale, p->production_info != NULL);
    for (uint32_t i = 0; i < p->number_of_inputs; ++i) molecule("i", i, &p->inputs[i]);
    for (uint32_t i = 0; i < p->number_of_outputs; ++i) molecule("o", i, &p->outputs[i]);
    if (p->production_info) {
        struct puzzle_production_info *x = p->production_info;
        printf("pf %d %d %d %u %u %u\n", x->shrink_left, x->shrink_right,
               x->isolate_inputs_from_outputs, x->number_of_cabinets,
               x->number_of_conduits, x->number_of_vials);
        for (uint32_t i = 0; i < x->number_of_cabinets; ++i) {
            printf("c %u %d %d ", i, (int)x->cabinets[i].position[0],
                   (int)x->cabinets[i].position[1]);
            hex_string(x->cabinets[i].type); printf("\n");
        }
        for (uint32_t i = 0; i < x->number_of_conduits; ++i) {
            struct puzzle_conduit *c = &x->conduits[i];
            printf("d %u %d %d %d %d %u\n", i,
                   (int)c->starting_position_a[0], (int)c->starting_position_a[1],
                   (int)c->starting_position_b[0], (int)c->starting_position_b[1],
                   c->number_of_hexes);
            for (uint32_t j = 0; j < c->number_of_hexes; ++j)
                printf("h %u %u %d %d\n", i, j, (int)c->hexes[j].offset[0],
                       (int)c->hexes[j].offset[1]);
        }
        for (uint32_t i = 0; i < x->number_of_vials; ++i)
            printf("v %u %d %d %u %u\n", i, (int)x->vials[i].position[0],
                   (int)x->vials[i].position[1], (unsigned)x->vials[i].style,
                   x->vials[i].count);
    }
    free_puzzle_file(p);
    return 0;
}
'''


def _pinned_omsim_uint64_bug(value: int) -> int:
    """Model parse.c's int32_t return bug without copying it into the native parser."""

    low = value & 0xFFFFFFFF
    signed = low if low < 0x80000000 else low - 0x100000000
    return signed % (1 << 64)


def _python_dump(parsed: ParsedPuzzle) -> str:
    lines = [
        f"name {parsed.name.hex()}",
        "header "
        f"{_pinned_omsim_uint64_bug(parsed.creator)} "
        f"{_pinned_omsim_uint64_bug(parsed.parts_available)} {len(parsed.inputs)} "
        f"{len(parsed.outputs)} {parsed.output_scale} "
        f"{int(parsed.production_info is not None)}",
    ]
    for kind, molecules in (("i", parsed.inputs), ("o", parsed.outputs)):
        for molecule_index, value in enumerate(molecules):
            lines.append(f"{kind} {molecule_index} {len(value.atoms)} {len(value.bonds)}")
            lines.extend(
                f"a {molecule_index} {index} {atom.atom_type} {atom.q} {atom.r}"
                for index, atom in enumerate(value.atoms)
            )
            lines.extend(
                f"b {molecule_index} {index} {bond.bond_type} {bond.a_q} {bond.a_r} "
                f"{bond.b_q} {bond.b_r}"
                for index, bond in enumerate(value.bonds)
            )
    info = parsed.production_info
    if info is not None:
        lines.append(
            f"pf {int(info.shrink_left)} {int(info.shrink_right)} "
            f"{int(info.isolate_inputs_from_outputs)} {len(info.cabinets)} "
            f"{len(info.conduits)} {len(info.vials)}"
        )
        lines.extend(
            f"c {index} {cabinet.q} {cabinet.r} {cabinet.cabinet_type.hex()}"
            for index, cabinet in enumerate(info.cabinets)
        )
        for index, conduit in enumerate(info.conduits):
            lines.append(
                f"d {index} {conduit.a_q} {conduit.a_r} {conduit.b_q} {conduit.b_r} "
                f"{len(conduit.hexes)}"
            )
            lines.extend(
                f"h {index} {hex_index} {item.q} {item.r}"
                for hex_index, item in enumerate(conduit.hexes)
            )
        lines.extend(
            f"v {index} {vial.q} {vial.r} {vial.style} {vial.count}"
            for index, vial in enumerate(info.vials)
        )
    return "\n".join(lines) + "\n"


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
    assert match is not None, "pinned omsim instruction availability function disappeared"
    return {
        opcode: 1 << int(bit)
        for opcode, bit in re.findall(
            r"case '(.)':\s*return 1ull << (\d+);",
            match.group("body"),
        )
    }


@pytest.mark.upstream
def test_native_parser_matches_pinned_omsim_parser_and_availability(tmp_path: Path) -> None:
    compiler = shutil.which("cc")
    assert compiler is not None, "puzzle parser differential contract requires a C compiler"

    source_root = tmp_path / "omsim"
    source_root.mkdir()
    fixtures: dict[str, bytes] = {}
    decode_source: str | None = None
    for path, member in iter_github_tarball_members(
        "ianh", "omsim", OmsimAdapter.pinned_revision
    ):
        if path in {"parse.c", "parse.h"}:
            (source_root / path).write_bytes(member.read())
        elif path == "decode.c":
            decode_source = member.read().decode("utf-8")
        elif path in _FIXTURES:
            fixtures[path] = member.read()

    assert decode_source is not None
    assert set(fixtures) == set(_FIXTURES)
    dumper_source = source_root / "dump-puzzle.c"
    dumper_source.write_text(_C_DUMPER, encoding="utf-8")
    dumper = source_root / "dump-puzzle"
    build = subprocess.run(
        [
            compiler,
            "-O2",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-pedantic",
            "-o",
            str(dumper),
            str(dumper_source),
            str(source_root / "parse.c"),
        ],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr

    part_requirements = _part_requirements(decode_source)
    instruction_requirements = _instruction_requirements(decode_source)
    assert part_requirements
    assert set(instruction_requirements) == set(_OPCODE_NAMES) - {"B"}

    production_states: set[bool] = set()
    saw_upstream_uint64_truncation = False
    for path in _FIXTURES:
        fixture = tmp_path / Path(path).name
        fixture.write_bytes(fixtures[path])
        upstream = subprocess.run(
            [str(dumper), str(fixture)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert upstream.returncode == 0, upstream.stderr

        parsed = parse_puzzle_bytes(fixtures[path])
        saw_upstream_uint64_truncation |= (
            parsed.creator != _pinned_omsim_uint64_bug(parsed.creator)
        )
        assert _python_dump(parsed) == upstream.stdout
        production_states.add(parsed.production_info is not None)

        evidence = decode_puzzle_definition_evidence(
            parsed,
            puzzle_id="om.puzzle.upstream-fixture",
            observation_ids=("om.observation.upstream-fixture",),
            puzzle_artifact_id="om.puzzle-artifact.upstream-fixture",
        )
        expected_parts = sorted(
            name
            for name, required in part_requirements.items()
            if parsed.parts_available & required == required
        )
        expected_instructions = sorted(
            name
            for opcode, name in _OPCODE_NAMES.items()
            if opcode == "B"
            or parsed.parts_available & instruction_requirements[opcode]
            == instruction_requirements[opcode]
        )
        assert evidence.claims["allowed_parts"] == expected_parts
        assert evidence.claims["allowed_instructions"] == expected_instructions
        assert evidence.claims["target_output_count"] == 6 * parsed.output_scale

    assert saw_upstream_uint64_truncation
    assert production_states == {False, True}
