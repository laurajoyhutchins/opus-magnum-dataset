from __future__ import annotations

import struct
from dataclasses import dataclass

from .errors import CorpusError

_SOLUTION_FORMAT_VERSION = 7
_MAX_PARTS = 9_999
_MAX_INSTRUCTIONS = 99_999
_MAX_TRACK_HEXES = 9_999
_MAX_CONDUIT_HEXES = 9_999


class SolutionParseError(CorpusError):
    """Raised when exact `.solution` bytes do not satisfy the supported format."""


@dataclass(frozen=True, slots=True)
class ParsedSolutionInstruction:
    cycle: int
    opcode: int


@dataclass(frozen=True, slots=True)
class ParsedSolutionPart:
    name: str
    x: int
    y: int
    size: int
    rotation: int
    input_output_index: int
    instructions: tuple[ParsedSolutionInstruction, ...]
    track_offsets: tuple[tuple[int, int], ...]
    arm_number: int
    conduit_id: int | None
    conduit_offsets: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class ParsedSolution:
    format_version: int
    puzzle_name: str
    solution_name: str
    solved: bool
    declared_cycles: int | None
    declared_cost: int | None
    declared_area: int | None
    declared_instructions: int | None
    parts: tuple[ParsedSolutionPart, ...]

    @property
    def declared_metrics(self) -> dict[str, int]:
        if not self.solved:
            return {}
        assert self.declared_cycles is not None
        assert self.declared_cost is not None
        assert self.declared_area is not None
        assert self.declared_instructions is not None
        return {
            "cycles": self.declared_cycles,
            "cost": self.declared_cost,
            "area": self.declared_area,
            "instructions": self.declared_instructions,
        }


class _Reader:
    def __init__(self, payload: bytes):
        self._payload = memoryview(payload)
        self._offset = 0

    @property
    def remaining(self) -> int:
        return len(self._payload) - self._offset

    def _read(self, byte_length: int, label: str) -> bytes:
        end = self._offset + byte_length
        if byte_length < 0 or end > len(self._payload):
            raise SolutionParseError(f"truncated solution while reading {label}")
        value = bytes(self._payload[self._offset : end])
        self._offset = end
        return value

    def u8(self, label: str) -> int:
        return self._read(1, label)[0]

    def u32(self, label: str) -> int:
        return struct.unpack("<I", self._read(4, label))[0]

    def i32(self, label: str) -> int:
        return struct.unpack("<i", self._read(4, label))[0]

    def count(self, label: str, maximum: int) -> int:
        value = self.u32(label)
        if value > maximum:
            raise SolutionParseError(f"{label} exceeds supported maximum {maximum}: {value}")
        return value

    def string(self, label: str) -> str:
        length = self._varint(f"{label} length")
        raw = self._read(length, label)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SolutionParseError(f"invalid UTF-8 in {label}") from exc

    def _varint(self, label: str) -> int:
        start = self._offset
        value = 0
        shift = 0
        for _ in range(5):
            byte = self.u8(label)
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                if value > 0xFFFFFFFF:
                    raise SolutionParseError(f"{label} varint exceeds uint32 range")
                encoded = bytes(self._payload[start : self._offset])
                if encoded != _encode_varint(value):
                    raise SolutionParseError(f"non-canonical {label} varint")
                return value
            shift += 7
        raise SolutionParseError(f"malformed {label} varint")


def _encode_varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            encoded.append(byte | 0x80)
        else:
            encoded.append(byte)
            return bytes(encoded)


def _read_metrics(reader: _Reader) -> tuple[bool, int | None, int | None, int | None, int | None]:
    metric_count = reader.u32("metric count")
    if metric_count == 0:
        return False, None, None, None, None
    if metric_count != 4:
        raise SolutionParseError(f"unsupported solution metric count {metric_count}")

    values: list[int] = []
    for expected_tag, label in enumerate(("cycles", "cost", "area", "instructions")):
        tag = reader.u32(f"{label} metric tag")
        if tag != expected_tag:
            raise SolutionParseError(
                f"invalid {label} metric tag: expected {expected_tag}, observed {tag}"
            )
        values.append(reader.u32(f"declared {label}"))
    cycles, cost, area, instructions = values
    return True, cycles, cost, area, instructions


def _read_offsets(reader: _Reader, label: str, maximum: int) -> tuple[tuple[int, int], ...]:
    count = reader.count(f"{label} count", maximum)
    return tuple(
        (
            reader.i32(f"{label} {index} x"),
            reader.i32(f"{label} {index} y"),
        )
        for index in range(count)
    )


def _read_part(reader: _Reader, index: int) -> ParsedSolutionPart:
    prefix = f"part {index}"
    name = reader.string(f"{prefix} name")
    marker = reader.u8(f"{prefix} marker")
    if marker != 1:
        raise SolutionParseError(f"invalid {prefix} marker {marker}")

    x = reader.i32(f"{prefix} x")
    y = reader.i32(f"{prefix} y")
    size = reader.u32(f"{prefix} size")
    rotation = reader.i32(f"{prefix} rotation")
    input_output_index = reader.u32(f"{prefix} input/output index")

    instruction_count = reader.count(f"{prefix} instruction count", _MAX_INSTRUCTIONS)
    instructions = tuple(
        ParsedSolutionInstruction(
            cycle=reader.i32(f"{prefix} instruction {instruction_index} cycle"),
            opcode=reader.u8(f"{prefix} instruction {instruction_index} opcode"),
        )
        for instruction_index in range(instruction_count)
    )

    track_offsets: tuple[tuple[int, int], ...] = ()
    if name == "track":
        track_offsets = _read_offsets(reader, f"{prefix} track hex", _MAX_TRACK_HEXES)

    arm_number = reader.u32(f"{prefix} arm number")

    conduit_id: int | None = None
    conduit_offsets: tuple[tuple[int, int], ...] = ()
    if name == "pipe":
        conduit_id = reader.u32(f"{prefix} conduit id")
        conduit_offsets = _read_offsets(reader, f"{prefix} conduit hex", _MAX_CONDUIT_HEXES)

    return ParsedSolutionPart(
        name=name,
        x=x,
        y=y,
        size=size,
        rotation=rotation,
        input_output_index=input_output_index,
        instructions=instructions,
        track_offsets=track_offsets,
        arm_number=arm_number,
        conduit_id=conduit_id,
        conduit_offsets=conduit_offsets,
    )


def parse_solution_bytes(payload: bytes) -> ParsedSolution:
    """Parse one exact format-7 Opus Magnum solution artifact deterministically."""

    reader = _Reader(payload)
    format_version = reader.u32("format version")
    if format_version != _SOLUTION_FORMAT_VERSION:
        raise SolutionParseError(
            f"unsupported solution format version {format_version}; "
            f"expected {_SOLUTION_FORMAT_VERSION}"
        )

    puzzle_name = reader.string("puzzle name")
    solution_name = reader.string("solution name")
    solved, cycles, cost, area, instructions = _read_metrics(reader)

    part_count = reader.count("part count", _MAX_PARTS)
    parts = tuple(_read_part(reader, index) for index in range(part_count))

    if reader.remaining:
        raise SolutionParseError(f"trailing bytes after solution record: {reader.remaining}")

    return ParsedSolution(
        format_version=format_version,
        puzzle_name=puzzle_name,
        solution_name=solution_name,
        solved=solved,
        declared_cycles=cycles,
        declared_cost=cost,
        declared_area=area,
        declared_instructions=instructions,
        parts=parts,
    )
