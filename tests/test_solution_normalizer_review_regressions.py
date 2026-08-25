from __future__ import annotations

import struct

from opus_corpus.normalization import SolutionNormalizationInput
from opus_corpus.solution_normalizer import OpusSolutionNormalizer


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _i32(value: int) -> bytes:
    return struct.pack("<i", value)


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return bytes([len(encoded)]) + encoded


def _rotated_conduit_solution() -> bytes:
    part = bytearray()
    part += _string("pipe")
    part += b"\x01"
    part += _i32(10)
    part += _i32(20)
    part += _u32(1)
    part += _i32(2)
    part += _u32(0)
    part += _u32(0)
    part += _u32(0)
    part += _u32(100)
    part += _u32(2)
    part += _i32(0) + _i32(0)
    part += _i32(1) + _i32(-1)

    payload = bytearray()
    payload += _u32(7)
    payload += _string("P001")
    payload += _string("rotated conduit")
    payload += _u32(0)
    payload += _u32(1)
    payload += part
    return bytes(payload)


def test_conduit_parameters_preserve_part_local_offsets_without_fake_absolute_geometry():
    record = OpusSolutionNormalizer().normalize(
        SolutionNormalizationInput(
            solution_id="om.solution.sha256." + "d" * 64,
            puzzle_id="om.puzzle.0001",
            solution_bytes=_rotated_conduit_solution(),
        )
    )

    parameters = record["parts"][0]["parameters"]
    assert parameters["conduit_id"] == 100
    assert parameters["conduit_offsets"] == [
        {"x": 0, "y": 0},
        {"x": 1, "y": -1},
    ]
    assert "conduit_coordinates" not in parameters
