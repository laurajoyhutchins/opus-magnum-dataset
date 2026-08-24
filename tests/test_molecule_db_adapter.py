from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.adapters import AdapterDataError
from opus_corpus.adapters.molecule_db import (
    MoleculeDbAdapter,
    MoleculeDbAtom,
    MoleculeDbBond,
    MoleculeDbMolecule,
    MoleculeDbMoleculeUse,
    MoleculeDbPuzzleSemantics,
)
from opus_corpus.collections import CollectionDefinition


def _collection(tmp_path: Path, rows: tuple[dict[str, str], ...]) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="test-collection",
        inventory_sha256="0" * 64,
        puzzle_count=len(rows),
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=rows,
        manifest={},
    )


def _row(
    puzzle_id: str,
    display_name: str,
    game_puzzle_id: str,
    leaderboard_key: str,
) -> dict[str, str]:
    return {
        "puzzle_id": puzzle_id,
        "display_name": display_name,
        "kind": "campaign",
        "group": "chapter-1",
        "game_puzzle_id": game_puzzle_id,
        "leaderboard_key": leaderboard_key,
        "puzzle_type": "normal",
    }


def _source(tmp_path: Path, puzzle_source: str, molecule_source: str) -> Path:
    root = tmp_path / "molecule-db"
    src = root / "src"
    src.mkdir(parents=True)
    (src / "puzzle.rs").write_text(puzzle_source, encoding="utf-8")
    (src / "molecules.rs").write_text(molecule_source, encoding="utf-8")
    return root


def _puzzle_source() -> str:
    return r'''
fn official(collection: OfficialCollection, zlbb_id: &'static str) -> Source {
    Source::Official { collection, zlbb_id }
}

puzzles! {
    StabilizedWater => "Stabilized Water", official(Prologue, "P007"),
    RefinedGold => "Refined Gold", official(Campaign(1), "P010"),
    CustomThing => "Custom Thing", other("https://example.invalid", &[]),
}
'''


def _molecule_source() -> str:
    return r'''
pub(crate) fn molecules() -> Vec<(Molecule, Vec<(Puzzle, u8, u8, Option<&'static str>)>)> {
    vec![
        (Molecule {
            atoms: collect![
                HexIndex { q: 0, r: 0 } => Atom::Salt,
                HexIndex { q: 1, r: 0 } => Atom::Water,
            ],
            bonds: collect![
                Bond {
                    start: HexIndex { q: 0, r: 0 },
                    end: HexIndex { q: 1, r: 0 },
                    ty: BondType::Triplex { red: true, black: true, yellow: false },
                },
            ],
        }, vec![
            (Puzzle::StabilizedWater, 1, 0, Some("Brine")),
            (Puzzle::CustomThing, 1, 0, None),
        ]),
        (Molecule {
            atoms: collect![HexIndex { q: -1, r: 2 } => Atom::Gold],
            bonds: collect![],
        }, vec![
            (Puzzle::StabilizedWater, 0, 2, Some("Stabilized Water")),
            (Puzzle::RefinedGold, 1, 1, None),
        ]),
    ]
}
'''


def test_load_official_catalog_parses_only_official_puzzles(tmp_path: Path):
    source_root = _source(tmp_path, _puzzle_source(), _molecule_source())

    catalog = MoleculeDbAdapter().load_official_catalog(source_root)

    assert set(catalog) == {"P007", "P010"}
    assert catalog["P007"].variant == "StabilizedWater"
    assert catalog["P007"].display_name == "Stabilized Water"
    assert catalog["P007"].source_collection == "Prologue"
    assert catalog["P010"].source_collection == "Campaign(1)"


def test_collection_semantics_preserves_topology_counts_and_names(tmp_path: Path):
    source_root = _source(tmp_path, _puzzle_source(), _molecule_source())
    collection = _collection(
        tmp_path,
        (
            _row("om.puzzle.0001", "Stabilized Water", "P007", "STABILIZED_WATER"),
            _row("om.puzzle.0002", "Refined Gold", "P010", "REFINED_GOLD"),
        ),
    )

    semantics = MoleculeDbAdapter().load_collection_semantics(collection, source_root)

    expected_brine = MoleculeDbMolecule(
        atoms=(
            MoleculeDbAtom(q=0, r=0, atom_type="Salt"),
            MoleculeDbAtom(q=1, r=0, atom_type="Water"),
        ),
        bonds=(
            MoleculeDbBond(
                start_q=0,
                start_r=0,
                end_q=1,
                end_r=0,
                bond_type="Triplex { red: true, black: true, yellow: false }",
            ),
        ),
    )
    expected_gold = MoleculeDbMolecule(
        atoms=(MoleculeDbAtom(q=-1, r=2, atom_type="Gold"),),
        bonds=(),
    )

    assert semantics == (
        MoleculeDbPuzzleSemantics(
            puzzle_id="om.puzzle.0001",
            game_puzzle_id="P007",
            variant="StabilizedWater",
            display_name="Stabilized Water",
            source_collection="Prologue",
            molecule_uses=(
                MoleculeDbMoleculeUse(
                    molecule=expected_brine,
                    reagent_count=1,
                    product_count=0,
                    name="Brine",
                ),
                MoleculeDbMoleculeUse(
                    molecule=expected_gold,
                    reagent_count=0,
                    product_count=2,
                    name="Stabilized Water",
                ),
            ),
        ),
        MoleculeDbPuzzleSemantics(
            puzzle_id="om.puzzle.0002",
            game_puzzle_id="P010",
            variant="RefinedGold",
            display_name="Refined Gold",
            source_collection="Campaign(1)",
            molecule_uses=(
                MoleculeDbMoleculeUse(
                    molecule=expected_gold,
                    reagent_count=1,
                    product_count=1,
                    name=None,
                ),
            ),
        ),
    )


def test_collection_semantics_preserves_source_display_name(tmp_path: Path):
    puzzle_source = _puzzle_source().replace(
        'StabilizedWater => "Stabilized Water"',
        'StabilizedWater => "Stabilized Water (source label)"',
    )
    source_root = _source(tmp_path, puzzle_source, _molecule_source())
    collection = _collection(
        tmp_path,
        (_row("om.puzzle.0001", "Stabilized Water", "P007", "STABILIZED_WATER"),),
    )

    semantics = MoleculeDbAdapter().load_collection_semantics(collection, source_root)

    assert semantics[0].display_name == "Stabilized Water (source label)"


def test_collection_semantics_fails_closed_on_missing_game_id(tmp_path: Path):
    source_root = _source(tmp_path, _puzzle_source(), _molecule_source())
    collection = _collection(
        tmp_path,
        (_row("om.puzzle.0001", "Unknown", "P999", "UNKNOWN"),),
    )

    with pytest.raises(AdapterDataError, match="missing"):
        MoleculeDbAdapter().load_collection_semantics(collection, source_root)


def test_collection_semantics_requires_reagent_and_product_evidence(tmp_path: Path):
    molecule_source = _molecule_source().replace(
        '(Puzzle::StabilizedWater, 0, 2, Some("Stabilized Water")),',
        '(Puzzle::CustomThing, 0, 2, Some("Stabilized Water")),',
    )
    source_root = _source(tmp_path, _puzzle_source(), molecule_source)
    collection = _collection(
        tmp_path,
        (_row("om.puzzle.0001", "Stabilized Water", "P007", "STABILIZED_WATER"),),
    )

    with pytest.raises(AdapterDataError, match="product"):
        MoleculeDbAdapter().load_collection_semantics(collection, source_root)


def test_molecule_parser_rejects_bond_to_missing_atom(tmp_path: Path):
    molecule_source = _molecule_source().replace(
        "end: HexIndex { q: 1, r: 0 },",
        "end: HexIndex { q: 9, r: 9 },",
        1,
    )
    source_root = _source(tmp_path, _puzzle_source(), molecule_source)

    with pytest.raises(AdapterDataError, match="bond endpoint"):
        MoleculeDbAdapter().load_molecule_uses(source_root)
