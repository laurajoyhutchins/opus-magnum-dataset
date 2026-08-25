from __future__ import annotations

import struct

import pytest

from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.github_source import iter_github_tarball_members
from opus_corpus.normalization import SolutionNormalizationInput
from opus_corpus.solution_normalizer import OpusSolutionNormalizer, SolutionNormalizationError
from opus_corpus.solution_parser import parse_solution_bytes


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _i32(value: int) -> bytes:
    return struct.pack("<i", value)


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    assert len(encoded) < 0x80
    return bytes([len(encoded)]) + encoded


def _part(name: str, *, track_offsets: tuple[tuple[int, int], ...] | None = None) -> bytes:
    payload = bytearray()
    payload += _string(name)
    payload += b"\x01"
    payload += _i32(0)
    payload += _i32(0)
    payload += _u32(1)
    payload += _i32(0)
    payload += _u32(0)
    payload += _u32(0)
    if track_offsets is not None:
        payload += _u32(len(track_offsets))
        for x, y in track_offsets:
            payload += _i32(x)
            payload += _i32(y)
    payload += _u32(0)
    return bytes(payload)


def _solution_with_part(part: bytes) -> bytes:
    return _u32(7) + _string("P001") + _string("fixture") + _u32(0) + _u32(1) + part


def test_solution_parser_treats_any_nonzero_solved_flag_as_metrics():
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


def test_solution_normalizer_rejects_empty_track_geometry():
    payload = _solution_with_part(_part("track", track_offsets=()))

    with pytest.raises(SolutionNormalizationError, match="track.*at least one"):
        OpusSolutionNormalizer().normalize(
            SolutionNormalizationInput(
                solution_id="om.solution.sha256." + "d" * 64,
                puzzle_id="om.puzzle.0004",
                solution_bytes=payload,
            )
        )


def test_solution_normalizer_rejects_empty_part_type():
    payload = _solution_with_part(_part(""))

    with pytest.raises(SolutionNormalizationError, match="part type"):
        OpusSolutionNormalizer().normalize(
            SolutionNormalizationInput(
                solution_id="om.solution.sha256." + "e" * 64,
                puzzle_id="om.puzzle.0005",
                solution_bytes=payload,
            )
        )


@pytest.mark.upstream
def test_solution_parser_matches_pinned_omsim_solution_fixture():
    fixture_path = "test/solution/easy/easy-conduit-easy-conduit-1.solution"
    payload = next(
        member.read()
        for path, member in iter_github_tarball_members(
            "ianh", "omsim", OmsimAdapter.pinned_revision
        )
        if path == fixture_path
    )

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
