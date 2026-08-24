from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..collections import CollectionDefinition
from .base import AdapterDataError
from .github import GitHubSourceAdapter

_PUZZLE_MODEL_PATH = Path("src/puzzle.rs")
_MOLECULE_MODEL_PATH = Path("src/molecules.rs")
_QUOTED_STRING = r'"(?:\\.|[^"\\])*"'
_OFFICIAL_ENTRY_RE = re.compile(
    rf"^\s*(?P<variant>[A-Za-z][A-Za-z0-9_]*)\s*=>\s*"
    rf"(?P<display>{_QUOTED_STRING})\s*,\s*"
    rf"official\(\s*(?P<collection>.+)\s*,\s*"
    rf"(?P<id>{_QUOTED_STRING})\s*\)\s*,\s*$"
)
_ATOM_RE = re.compile(
    r"^\s*HexIndex\s*\{\s*q:\s*(?P<q>-?\d+)\s*,\s*"
    r"r:\s*(?P<r>-?\d+)\s*\}\s*=>\s*"
    r"Atom::(?P<type>[A-Za-z][A-Za-z0-9_]*)\s*$"
)
_BOND_RE = re.compile(
    r"^\s*Bond\s*\{\s*start:\s*HexIndex\s*\{\s*"
    r"q:\s*(?P<start_q>-?\d+)\s*,\s*r:\s*(?P<start_r>-?\d+)\s*\}\s*,\s*"
    r"end:\s*HexIndex\s*\{\s*q:\s*(?P<end_q>-?\d+)\s*,\s*"
    r"r:\s*(?P<end_r>-?\d+)\s*\}\s*,\s*"
    r"ty:\s*BondType::(?P<type>[A-Za-z][A-Za-z0-9_]*)\s*,?\s*\}\s*$"
)
_APPEARANCE_RE = re.compile(
    rf"^\s*\(\s*Puzzle::(?P<variant>[A-Za-z][A-Za-z0-9_]*)\s*,\s*"
    rf"(?P<reagents>\d+)\s*,\s*(?P<products>\d+)\s*,\s*"
    rf"(?P<name>Some\(\s*{_QUOTED_STRING}\s*\)|None)\s*\)\s*$"
)


@dataclass(frozen=True)
class MoleculeDbAtom:
    q: int
    r: int
    atom_type: str


@dataclass(frozen=True)
class MoleculeDbBond:
    start_q: int
    start_r: int
    end_q: int
    end_r: int
    bond_type: str


@dataclass(frozen=True)
class MoleculeDbMolecule:
    atoms: tuple[MoleculeDbAtom, ...]
    bonds: tuple[MoleculeDbBond, ...]


@dataclass(frozen=True)
class MoleculeDbMoleculeUse:
    molecule: MoleculeDbMolecule
    reagent_count: int
    product_count: int
    name: str | None


@dataclass(frozen=True)
class MoleculeDbOfficialPuzzle:
    variant: str
    display_name: str
    source_collection: str
    game_puzzle_id: str


@dataclass(frozen=True)
class MoleculeDbPuzzleSemantics:
    puzzle_id: str
    game_puzzle_id: str
    variant: str
    display_name: str
    source_collection: str
    molecule_uses: tuple[MoleculeDbMoleculeUse, ...]


def _read_source(path: Path, source_id: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AdapterDataError(
            f"source adapter {source_id!r} could not read {path}"
        ) from exc


def _find_matching(text: str, opening: int, open_char: str, close_char: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(opening, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    raise AdapterDataError(f"unclosed {open_char!r} in molecule-db source")


def _split_top_level(text: str) -> tuple[str, ...]:
    parts: list[str] = []
    start = 0
    stack: list[str] = []
    closing = {"(": ")", "[": "]", "{": "}"}
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in closing:
            stack.append(char)
        elif char in closing.values():
            if not stack or closing[stack.pop()] != char:
                raise AdapterDataError("unbalanced delimiter in molecule-db source")
        elif char == "," and not stack:
            part = text[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1

    if in_string or stack:
        raise AdapterDataError("unbalanced molecule-db source expression")
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return tuple(parts)


def _extract_macro_list(text: str, marker: str) -> str:
    offset = text.find(marker)
    if offset < 0:
        raise AdapterDataError(f"molecule-db source is missing {marker!r}")
    opening = text.find("[", offset + len(marker))
    if opening < 0:
        raise AdapterDataError(f"molecule-db source has malformed {marker!r}")
    closing = _find_matching(text, opening, "[", "]")
    return text[opening + 1 : closing]


def _parse_optional_name(value: str) -> str | None:
    if value.strip() == "None":
        return None
    opening = value.find("(")
    closing = value.rfind(")")
    if opening < 0 or closing <= opening:
        raise AdapterDataError("malformed molecule-db molecule name")
    return json.loads(value[opening + 1 : closing].strip())


class MoleculeDbAdapter(GitHubSourceAdapter):
    source_id = "molecule-db"
    pinned_revision = "6f3cd8068428ef96ac6426d092c3523da359ec76"
    repository = "fenhl/molecule-db"

    def load_official_catalog(
        self,
        source_root: Path,
    ) -> dict[str, MoleculeDbOfficialPuzzle]:
        """Parse official puzzle identities without treating them as membership authority."""
        text = _read_source(source_root / _PUZZLE_MODEL_PATH, self.source_id)
        marker = "puzzles!"
        marker_offset = text.find(marker)
        if marker_offset < 0:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} could not locate puzzles macro"
            )
        opening = text.find("{", marker_offset + len(marker))
        if opening < 0:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} found malformed puzzles macro"
            )
        closing = _find_matching(text, opening, "{", "}")
        body = "\n".join(
            line
            for line in text[opening + 1 : closing].splitlines()
            if not line.lstrip().startswith("//")
        )

        catalog: dict[str, MoleculeDbOfficialPuzzle] = {}
        variants: set[str] = set()
        official_lines = [line for line in body.splitlines() if "official(" in line]
        for line in official_lines:
            match = _OFFICIAL_ENTRY_RE.fullmatch(line)
            if match is None:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} encountered unparsed official puzzle data"
                )
            variant = match.group("variant")
            game_puzzle_id = json.loads(match.group("id"))
            if variant in variants:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found duplicate puzzle variant {variant!r}"
                )
            if game_puzzle_id in catalog:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found duplicate game puzzle id "
                    f"{game_puzzle_id!r}"
                )
            variants.add(variant)
            catalog[game_puzzle_id] = MoleculeDbOfficialPuzzle(
                variant=variant,
                display_name=json.loads(match.group("display")),
                source_collection=match.group("collection").strip(),
                game_puzzle_id=game_puzzle_id,
            )

        if not catalog:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} found no official puzzles"
            )
        return catalog

    def load_molecule_uses(
        self,
        source_root: Path,
    ) -> dict[str, tuple[MoleculeDbMoleculeUse, ...]]:
        """Parse molecule topology and per-puzzle reagent/product multiplicities."""
        text = _read_source(source_root / _MOLECULE_MODEL_PATH, self.source_id)
        function_offset = text.find("pub(crate) fn molecules()")
        if function_offset < 0:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} could not locate molecules function"
            )
        body_offset = text.find("vec![", function_offset)
        if body_offset < 0:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} could not locate molecule table"
            )
        table_open = text.find("[", body_offset)
        table_close = _find_matching(text, table_open, "[", "]")
        table = text[table_open + 1 : table_close]

        uses: defaultdict[str, list[MoleculeDbMoleculeUse]] = defaultdict(list)
        cursor = 0
        molecule_count = 0
        while True:
            molecule_start = table.find("Molecule {", cursor)
            if molecule_start < 0:
                break
            brace_open = table.find("{", molecule_start)
            brace_close = _find_matching(table, brace_open, "{", "}")
            molecule_body = table[brace_open + 1 : brace_close]
            molecule = self._parse_molecule(molecule_body)

            after_molecule = brace_close + 1
            appearance_marker = table.find("vec![", after_molecule)
            next_molecule = table.find("Molecule {", after_molecule)
            if appearance_marker < 0 or (
                next_molecule >= 0 and next_molecule < appearance_marker
            ):
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found molecule without appearance data"
                )
            between = table[after_molecule:appearance_marker]
            if between.strip().rstrip(",").strip():
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found unexpected molecule table data"
                )

            appearance_open = table.find("[", appearance_marker)
            appearance_close = _find_matching(table, appearance_open, "[", "]")
            appearance_body = table[appearance_open + 1 : appearance_close]
            appearances = _split_top_level(appearance_body)
            if not appearances:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found molecule without puzzle appearances"
                )
            for expression in appearances:
                match = _APPEARANCE_RE.fullmatch(expression)
                if match is None:
                    raise AdapterDataError(
                        f"source adapter {self.source_id!r} encountered unparsed "
                        "molecule appearance"
                    )
                reagent_count = int(match.group("reagents"))
                product_count = int(match.group("products"))
                if reagent_count == 0 and product_count == 0:
                    raise AdapterDataError(
                        f"source adapter {self.source_id!r} found zero-count molecule appearance"
                    )
                uses[match.group("variant")].append(
                    MoleculeDbMoleculeUse(
                        molecule=molecule,
                        reagent_count=reagent_count,
                        product_count=product_count,
                        name=_parse_optional_name(match.group("name")),
                    )
                )

            molecule_count += 1
            cursor = appearance_close + 1

        if molecule_count == 0:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} found no molecule entries"
            )
        return {variant: tuple(items) for variant, items in uses.items()}

    def _parse_molecule(self, body: str) -> MoleculeDbMolecule:
        atoms_body = _extract_macro_list(body, "atoms: collect!")
        bonds_body = _extract_macro_list(body, "bonds: collect!")

        atoms: list[MoleculeDbAtom] = []
        positions: set[tuple[int, int]] = set()
        for expression in _split_top_level(atoms_body):
            match = _ATOM_RE.fullmatch(expression)
            if match is None:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} encountered unparsed atom data"
                )
            atom = MoleculeDbAtom(
                q=int(match.group("q")),
                r=int(match.group("r")),
                atom_type=match.group("type"),
            )
            position = (atom.q, atom.r)
            if position in positions:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found duplicate atom position {position}"
                )
            positions.add(position)
            atoms.append(atom)

        if not atoms:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} found molecule without atoms"
            )

        bonds: list[MoleculeDbBond] = []
        for expression in _split_top_level(bonds_body):
            match = _BOND_RE.fullmatch(expression)
            if match is None:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} encountered unparsed bond data"
                )
            bond = MoleculeDbBond(
                start_q=int(match.group("start_q")),
                start_r=int(match.group("start_r")),
                end_q=int(match.group("end_q")),
                end_r=int(match.group("end_r")),
                bond_type=match.group("type"),
            )
            endpoints = {
                (bond.start_q, bond.start_r),
                (bond.end_q, bond.end_r),
            }
            if not endpoints.issubset(positions):
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found bond endpoint without atom"
                )
            bonds.append(bond)

        return MoleculeDbMolecule(atoms=tuple(atoms), bonds=tuple(bonds))

    def load_collection_semantics(
        self,
        collection: CollectionDefinition,
        source_root: Path,
    ) -> tuple[MoleculeDbPuzzleSemantics, ...]:
        """Reconcile independent semantic evidence to canonical collection identities."""
        catalog = self.load_official_catalog(source_root)
        uses_by_variant = self.load_molecule_uses(source_root)
        semantics: list[MoleculeDbPuzzleSemantics] = []
        errors: list[str] = []

        for row in collection.inventory_rows:
            game_puzzle_id = row["game_puzzle_id"]
            official = catalog.get(game_puzzle_id)
            if official is None:
                errors.append(f"{game_puzzle_id}: missing from molecule-db official catalog")
                continue
            if official.display_name != row["display_name"]:
                errors.append(
                    f"{game_puzzle_id}: display_name expected {row['display_name']!r}, "
                    f"observed {official.display_name!r}"
                )
                continue

            molecule_uses = uses_by_variant.get(official.variant, ())
            if not any(use.reagent_count for use in molecule_uses):
                errors.append(f"{game_puzzle_id}: missing reagent semantic evidence")
            if not any(use.product_count for use in molecule_uses):
                errors.append(f"{game_puzzle_id}: missing product semantic evidence")
            semantics.append(
                MoleculeDbPuzzleSemantics(
                    puzzle_id=row["puzzle_id"],
                    game_puzzle_id=game_puzzle_id,
                    variant=official.variant,
                    display_name=official.display_name,
                    source_collection=official.source_collection,
                    molecule_uses=molecule_uses,
                )
            )

        if errors:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} does not reconcile with collection "
                f"{collection.collection_id!r}: {'; '.join(errors)}"
            )
        return tuple(semantics)
