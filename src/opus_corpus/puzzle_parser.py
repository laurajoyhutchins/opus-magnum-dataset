from __future__ import annotations

from dataclasses import dataclass

from .errors import CorpusError

_FORMAT_VERSION = 3
_MAX_CONTAINER_COUNT = 100_000
_MAX_STRING_BYTES = 1_048_576


class PuzzleParseError(CorpusError):
    """Raised when exact puzzle bytes do not satisfy the supported format contract."""


@dataclass(frozen=True, slots=True)
class ParsedPuzzleAtom:
    atom_type: int
    q: int
    r: int


@dataclass(frozen=True, slots=True)
class ParsedPuzzleBond:
    bond_type: int
    a_q: int
    a_r: int
    b_q: int
    b_r: int


@dataclass(frozen=True, slots=True)
class ParsedPuzzleMolecule:
    atoms: tuple[ParsedPuzzleAtom, ...]
    bonds: tuple[ParsedPuzzleBond, ...]


@dataclass(frozen=True, slots=True)
class ParsedPuzzleCabinet:
    q: int
    r: int
    cabinet_type: bytes


@dataclass(frozen=True, slots=True)
class ParsedPuzzleConduitHex:
    q: int
    r: int


@dataclass(frozen=True, slots=True)
class ParsedPuzzleConduit:
    a_q: int
    a_r: int
    b_q: int
    b_r: int
    hexes: tuple[ParsedPuzzleConduitHex, ...]


@dataclass(frozen=True, slots=True)
class ParsedPuzzleVial:
    q: int
    r: int
    style: int
    count: int


@dataclass(frozen=True, slots=True)
class ParsedPuzzleProductionInfo:
    shrink_left: bool
    shrink_right: bool
    isolate_inputs_from_outputs: bool
    cabinets: tuple[ParsedPuzzleCabinet, ...]
    conduits: tuple[ParsedPuzzleConduit, ...]
    vials: tuple[ParsedPuzzleVial, ...]


@dataclass(frozen=True, slots=True)
class ParsedPuzzle:
    format_version: int
    name: bytes
    creator: int
    parts_available: int
    inputs: tuple[ParsedPuzzleMolecule, ...]
    outputs: tuple[ParsedPuzzleMolecule, ...]
    output_scale: int
    production_info: ParsedPuzzleProductionInfo | None


class _Reader:
    def __init__(self, payload: bytes) -> None:
        self._payload = memoryview(payload)
        self._offset = 0

    @property
    def remaining(self) -> int:
        return len(self._payload) - self._offset

    def _read(self, length: int, *, label: str) -> memoryview:
        if length < 0 or self.remaining < length:
            raise PuzzleParseError(f"truncated puzzle while reading {label}")
        start = self._offset
        self._offset += length
        return self._payload[start : start + length]

    def u8(self, *, label: str) -> int:
        return int(self._read(1, label=label)[0])

    def i8(self, *, label: str) -> int:
        value = self.u8(label=label)
        return value if value < 0x80 else value - 0x100

    def u32(self, *, label: str) -> int:
        return int.from_bytes(self._read(4, label=label), "little", signed=False)

    def u64(self, *, label: str) -> int:
        return int.from_bytes(self._read(8, label=label), "little", signed=False)

    def count(self, *, label: str) -> int:
        value = self.u32(label=f"{label} count")
        if value > _MAX_CONTAINER_COUNT:
            raise PuzzleParseError(
                f"{label} count {value} exceeds parser limit {_MAX_CONTAINER_COUNT}"
            )
        return value

    def boolean(self, *, label: str) -> bool:
        value = self.u8(label=label)
        if value not in {0, 1}:
            raise PuzzleParseError(f"invalid {label}: expected 0 or 1, got {value}")
        return bool(value)

    def string(self, *, label: str) -> bytes:
        length = 0
        for shift in range(0, 35, 7):
            byte = self.u8(label=f"{label} length")
            if shift == 28 and byte > 0x0F:
                raise PuzzleParseError(f"invalid {label} length encoding")
            length |= (byte & 0x7F) << shift
            if not byte & 0x80:
                if length > _MAX_STRING_BYTES:
                    raise PuzzleParseError(
                        f"{label} length {length} exceeds parser limit {_MAX_STRING_BYTES}"
                    )
                return bytes(self._read(length, label=label))
        raise PuzzleParseError(f"invalid {label} length encoding")


def _parse_molecule(reader: _Reader, *, label: str) -> ParsedPuzzleMolecule:
    atom_count = reader.count(label=f"{label} atom")
    atoms: list[ParsedPuzzleAtom] = []
    positions: set[tuple[int, int]] = set()
    for index in range(atom_count):
        atom = ParsedPuzzleAtom(
            atom_type=reader.u8(label=f"{label} atom {index} type"),
            q=reader.i8(label=f"{label} atom {index} q"),
            r=reader.i8(label=f"{label} atom {index} r"),
        )
        position = (atom.q, atom.r)
        if position in positions:
            raise PuzzleParseError(
                f"{label}: duplicate atom coordinate ({atom.q}, {atom.r})"
            )
        positions.add(position)
        atoms.append(atom)

    bond_count = reader.count(label=f"{label} bond")
    bonds: list[ParsedPuzzleBond] = []
    for index in range(bond_count):
        bond = ParsedPuzzleBond(
            bond_type=reader.u8(label=f"{label} bond {index} type"),
            a_q=reader.i8(label=f"{label} bond {index} a_q"),
            a_r=reader.i8(label=f"{label} bond {index} a_r"),
            b_q=reader.i8(label=f"{label} bond {index} b_q"),
            b_r=reader.i8(label=f"{label} bond {index} b_r"),
        )
        first = (bond.a_q, bond.a_r)
        second = (bond.b_q, bond.b_r)
        if first not in positions or second not in positions:
            raise PuzzleParseError(
                f"{label}: bond endpoint does not reference an atom coordinate"
            )
        bonds.append(bond)
    return ParsedPuzzleMolecule(atoms=tuple(atoms), bonds=tuple(bonds))


def _parse_molecules(reader: _Reader, *, label: str) -> tuple[ParsedPuzzleMolecule, ...]:
    count = reader.count(label=label)
    return tuple(_parse_molecule(reader, label=f"{label[:-1]} {index}") for index in range(count))


def _parse_production_info(reader: _Reader) -> ParsedPuzzleProductionInfo:
    shrink_left = reader.boolean(label="production shrink_left")
    shrink_right = reader.boolean(label="production shrink_right")
    isolate = reader.boolean(label="production isolate_inputs_from_outputs")

    cabinets: list[ParsedPuzzleCabinet] = []
    for index in range(reader.count(label="production cabinet")):
        cabinets.append(
            ParsedPuzzleCabinet(
                q=reader.i8(label=f"production cabinet {index} q"),
                r=reader.i8(label=f"production cabinet {index} r"),
                cabinet_type=reader.string(label=f"production cabinet {index} type"),
            )
        )

    conduits: list[ParsedPuzzleConduit] = []
    for index in range(reader.count(label="production conduit")):
        a_q = reader.i8(label=f"production conduit {index} a_q")
        a_r = reader.i8(label=f"production conduit {index} a_r")
        b_q = reader.i8(label=f"production conduit {index} b_q")
        b_r = reader.i8(label=f"production conduit {index} b_r")
        hexes = tuple(
            ParsedPuzzleConduitHex(
                q=reader.i8(label=f"production conduit {index} hex {hex_index} q"),
                r=reader.i8(label=f"production conduit {index} hex {hex_index} r"),
            )
            for hex_index in range(reader.count(label=f"production conduit {index} hex"))
        )
        conduits.append(
            ParsedPuzzleConduit(
                a_q=a_q,
                a_r=a_r,
                b_q=b_q,
                b_r=b_r,
                hexes=hexes,
            )
        )

    vials: list[ParsedPuzzleVial] = []
    for index in range(reader.count(label="production vial")):
        vials.append(
            ParsedPuzzleVial(
                q=reader.i8(label=f"production vial {index} q"),
                r=reader.i8(label=f"production vial {index} r"),
                style=reader.u8(label=f"production vial {index} style"),
                count=reader.u32(label=f"production vial {index} count"),
            )
        )

    return ParsedPuzzleProductionInfo(
        shrink_left=shrink_left,
        shrink_right=shrink_right,
        isolate_inputs_from_outputs=isolate,
        cabinets=tuple(cabinets),
        conduits=tuple(conduits),
        vials=tuple(vials),
    )


def parse_puzzle_bytes(payload: bytes) -> ParsedPuzzle:
    """Parse exact Opus Magnum format-3 puzzle bytes with strict bounds."""

    if not isinstance(payload, bytes):
        raise PuzzleParseError("puzzle payload must be bytes")
    reader = _Reader(payload)
    version = reader.u32(label="format version")
    if version != _FORMAT_VERSION:
        raise PuzzleParseError(f"unsupported puzzle format version {version}")

    name = reader.string(label="puzzle name")
    creator = reader.u64(label="creator")
    parts_available = reader.u64(label="parts_available")
    inputs = _parse_molecules(reader, label="inputs")
    outputs = _parse_molecules(reader, label="outputs")
    output_scale = reader.u32(label="output_scale")
    is_production = reader.boolean(label="production flag")
    production_info = _parse_production_info(reader) if is_production else None

    if reader.remaining:
        raise PuzzleParseError(f"puzzle has {reader.remaining} trailing byte(s)")

    return ParsedPuzzle(
        format_version=version,
        name=name,
        creator=creator,
        parts_available=parts_available,
        inputs=inputs,
        outputs=outputs,
        output_scale=output_scale,
        production_info=production_info,
    )
