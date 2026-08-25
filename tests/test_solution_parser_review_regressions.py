from __future__ import annotations

import struct

import pytest

from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.github_source import download_github_tarball, tarball_files
from opus_corpus.solution_parser import parse_solution_bytes


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    assert len(encoded) < 0x80
    return bytes([len(encoded)]) + encoded


def test_solution_parser_treats_nonzero_header_field_as_solved_flag():
    payload = bytearray()
    payload += _u32(7)
    payload += _string("P001")
    payload += _string("solved-flag-one")
    payload += _u32(1)
    for tag, value in enumerate((12, 34, 56, 78)):
        payload += _u32(tag)
        payload += _u32(value)
    payload += _u32(0)

    parsed = parse_solution_bytes(bytes(payload))

    assert parsed.solved is True
    assert parsed.declared_metrics == {
        "cycles": 12,
        "cost": 34,
        "area": 56,
        "instructions": 78,
    }
    assert parsed.parts == ()


@pytest.mark.upstream
def test_solution_parser_matches_pinned_omsim_solution_fixture():
    tarball = download_github_tarball("ianh", "omsim", OmsimAdapter.pinned_revision)
    files = tarball_files(tarball, suffix=".solution")
    payload = files["test/solution/easy/easy-conduit-easy-conduit-1.solution"]

    parsed = parse_solution_bytes(payload)

    assert parsed.format_version == 7
    assert parsed.puzzle_name == "easy-conduit"
    assert parsed.solution_name == "NEW SOLUTION 1"
    assert parsed.declared_metrics == {
        "cycles": 26,
        "cost": 40,
        "area": 29,
        "instructions": 8,
    }
    assert len(parsed.parts) == 6
