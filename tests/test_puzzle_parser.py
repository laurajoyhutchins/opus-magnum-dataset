from __future__ import annotations

import struct

import pytest

from opus_corpus.errors import CorpusError


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def _i8(value: int) -> bytes:
    return struct.pack("<b", value)


def _string(value: bytes) -> bytes:
    length = len(value)
    encoded = bytearray()
    while length >= 0x80:
        encoded.append((length & 0x7F) | 0x80)
        length >>= 7
    encoded.append(length)
    return bytes(encoded) + value


def _molecule(
    atoms: list[tuple[int, int, int]],
    bonds: list[tuple[int, int, int, int, int]],
) -> bytes:
    result = bytearray(_u32(len(atoms)))
    for atom_type, q, r in atoms:
        result += bytes([atom_type]) + _i8(q) + _i8(r)
    result += _u32(len(bonds))
    for bond_type, a_q, a_r, b_q, b_r in bonds:
        result += bytes([bond_type]) + _i8(a_q) + _i8(a_r) + _i8(b_q) + _i8(b_r)
    return bytes(result)


def _puzzle(
    *,
    name: bytes = b"Strict Fixture",
    creator: int = 17,
    parts_available: int = 0,
    inputs: list[bytes] | None = None,
    outputs: list[bytes] | None = None,
    output_scale: int = 1,
    production: bytes = b"\x00",
) -> bytes:
    inputs = inputs if inputs is not None else [_molecule([(1, 0, 0)], [])]
    outputs = outputs if outputs is not None else [_molecule([(2, 0, 0)], [])]
    result = bytearray(_u32(3))
    result += _string(name)
    result += _u64(creator)
    result += _u64(parts_available)
    result += _u32(len(inputs))
    for molecule in inputs:
        result += molecule
    result += _u32(len(outputs))
    for molecule in outputs:
        result += molecule
    result += _u32(output_scale)
    result += production
    return bytes(result)


def test_parse_minimal_format_3_puzzle() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    payload = _puzzle(
        name=b"Parser Fixture",
        creator=0x0102030405060708,
        parts_available=(1 << 0) | (1 << 8) | (1 << 22),
        inputs=[_molecule([(1, -1, 2)], [])],
        outputs=[
            _molecule(
                [(2, 0, 0), (4, 1, 0)],
                [(9, 0, 0, 1, 0)],
            )
        ],
        output_scale=2,
    )

    parsed = parse_puzzle_bytes(payload)

    assert parsed.format_version == 3
    assert parsed.name == b"Parser Fixture"
    assert parsed.creator == 0x0102030405060708
    assert parsed.parts_available == (1 << 0) | (1 << 8) | (1 << 22)
    assert parsed.output_scale == 2
    assert parsed.production_info is None
    assert parsed.inputs[0].atoms[0].atom_type == 1
    assert (parsed.inputs[0].atoms[0].q, parsed.inputs[0].atoms[0].r) == (-1, 2)
    assert parsed.outputs[0].bonds[0].bond_type == 9
    assert (
        parsed.outputs[0].bonds[0].a_q,
        parsed.outputs[0].bonds[0].a_r,
        parsed.outputs[0].bonds[0].b_q,
        parsed.outputs[0].bonds[0].b_r,
    ) == (0, 0, 1, 0)


def test_parse_production_fields() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    production = bytearray(b"\x01")
    production += b"\x01\x00\x01"
    production += _u32(1)
    production += _i8(-2) + _i8(3) + _string(b"SmallWide")
    production += _u32(1)
    production += _i8(1) + _i8(2) + _i8(-3) + _i8(4)
    production += _u32(2)
    production += _i8(0) + _i8(0) + _i8(1) + _i8(-1)
    production += _u32(1)
    production += _i8(5) + _i8(-6) + b"\x02" + _u32(7)

    parsed = parse_puzzle_bytes(_puzzle(production=bytes(production)))
    info = parsed.production_info
    assert info is not None
    assert info.shrink_left is True
    assert info.shrink_right is False
    assert info.isolate_inputs_from_outputs is True
    assert info.cabinets[0].cabinet_type == b"SmallWide"
    assert (info.cabinets[0].q, info.cabinets[0].r) == (-2, 3)
    assert (info.conduits[0].a_q, info.conduits[0].a_r) == (1, 2)
    assert (info.conduits[0].b_q, info.conduits[0].b_r) == (-3, 4)
    assert [(item.q, item.r) for item in info.conduits[0].hexes] == [(0, 0), (1, -1)]
    assert (info.vials[0].q, info.vials[0].r, info.vials[0].style, info.vials[0].count) == (
        5,
        -6,
        2,
        7,
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"\x03\x00",
        _u32(3) + b"\x05ab",
        _u32(3) + _string(b"x") + _u64(0) + _u64(0) + _u32(1),
        _puzzle(production=b"\x01\x01\x00"),
    ],
)
def test_truncated_puzzle_data_fails_closed(payload: bytes) -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    with pytest.raises(CorpusError, match="truncated"):
        parse_puzzle_bytes(payload)


def test_unsupported_puzzle_version_fails_closed() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    with pytest.raises(CorpusError, match="unsupported.*version"):
        parse_puzzle_bytes(_u32(2))


def test_excessive_container_count_fails_before_allocation() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    payload = _u32(3) + _string(b"x") + _u64(0) + _u64(0) + _u32(0xFFFFFFFF)
    with pytest.raises(CorpusError, match="count"):
        parse_puzzle_bytes(payload)


def test_bond_endpoint_must_reference_an_atom_coordinate() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    invalid = _molecule([(1, 0, 0)], [(1, 0, 0, 9, 9)])
    with pytest.raises(CorpusError, match="bond endpoint"):
        parse_puzzle_bytes(_puzzle(inputs=[invalid]))


def test_duplicate_atom_coordinates_fail_closed() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    invalid = _molecule([(1, 0, 0), (2, 0, 0)], [])
    with pytest.raises(CorpusError, match="duplicate atom coordinate"):
        parse_puzzle_bytes(_puzzle(inputs=[invalid]))


def test_non_boolean_production_flag_fails_closed() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    with pytest.raises(CorpusError, match="production flag"):
        parse_puzzle_bytes(_puzzle(production=b"\x02"))


def test_trailing_bytes_fail_closed() -> None:
    from opus_corpus.puzzle_parser import parse_puzzle_bytes

    with pytest.raises(CorpusError, match="trailing"):
        parse_puzzle_bytes(_puzzle() + b"\x00")
