from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from opus_corpus import github_source
from opus_corpus.adapters.molecule_db import MoleculeDbAdapter
from opus_corpus.collections import CollectionDefinition
from opus_corpus.errors import CorpusError

PUZZLE_SOURCE = b'''\
puzzles! {
    AlphaPuzzle => "Alpha Puzzle", official(Campaign(1), "P001"),
}
'''
MOLECULE_SOURCE = b'''\
pub(crate) fn molecules() -> Vec<()> {
    vec![
        (Molecule { atoms: collect![HexIndex { q: 0, r: 0 } => Atom::Salt, HexIndex { q: 1, r: 0 } => Atom::Fire], bonds: collect![Bond { start: HexIndex { q: 0, r: 0 }, end: HexIndex { q: 1, r: 0 }, ty: BondType::Normal }] }, vec![
            (Puzzle::AlphaPuzzle, 1, 1, Some("Alpha Molecule")),
        ]),
    ]
}
'''


def _collection(tmp_path: Path, game_puzzle_id: str = "P001") -> CollectionDefinition:
    row = {
        "puzzle_id": "om.puzzle.0001",
        "display_name": "Alpha Puzzle",
        "kind": "official",
        "group": "chapter-1",
        "game_puzzle_id": game_puzzle_id,
        "leaderboard_key": "P001",
        "puzzle_type": "production",
    }
    return CollectionDefinition(
        collection_id="test-collection",
        inventory_sha256="0" * 64,
        puzzle_count=1,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=(row,),
        manifest={},
    )


def _tarball(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, payload in sorted(files.items()):
            info = tarfile.TarInfo(f"fenhl-molecule-db-pinned/{path}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_fetch_caches_only_semantic_source_files_with_provenance(monkeypatch, tmp_path: Path):
    payload = _tarball(
        {
            "src/puzzle.rs": PUZZLE_SOURCE,
            "src/molecules.rs": MOLECULE_SOURCE,
            "README.md": b"not semantic evidence",
        }
    )
    monkeypatch.setattr(github_source, "download_github_tarball", lambda *args: payload)

    result = MoleculeDbAdapter().fetch(_collection(tmp_path), tmp_path / "cache")

    assert result.candidate_count == 2
    assert result.puzzles_covered == 1
    receipts = sorted((tmp_path / "cache" / "receipts" / "molecule-db").rglob("*.json"))
    assert len(receipts) == 2
    observed = [json.loads(path.read_text()) for path in receipts]
    assert {item["upstream_path"] for item in observed} == {"src/puzzle.rs", "src/molecules.rs"}
    assert {item["revision"] for item in observed} == {MoleculeDbAdapter.pinned_revision}
    assert {item["rights_status"] for item in observed} == {"local_fetch_only"}


def test_parse_collection_semantics_reconciles_topology_by_game_puzzle_id(tmp_path: Path):
    semantics = MoleculeDbAdapter().parse_collection_semantics(
        _collection(tmp_path),
        puzzle_source=PUZZLE_SOURCE,
        molecules_source=MOLECULE_SOURCE,
    )

    assert len(semantics) == 1
    puzzle = semantics[0]
    assert puzzle.puzzle_id == "om.puzzle.0001"
    assert puzzle.game_puzzle_id == "P001"
    assert puzzle.variant == "AlphaPuzzle"
    assert puzzle.source_collection == "Campaign(1)"
    assert len(puzzle.molecule_uses) == 1
    use = puzzle.molecule_uses[0]
    assert (use.reagent_count, use.product_count, use.name) == (1, 1, "Alpha Molecule")
    assert [(atom.q, atom.r, atom.atom_type) for atom in use.molecule.atoms] == [
        (0, 0, "Salt"),
        (1, 0, "Fire"),
    ]
    assert [
        (bond.start_q, bond.start_r, bond.end_q, bond.end_r, bond.bond_type)
        for bond in use.molecule.bonds
    ] == [(0, 0, 1, 0, "Normal")]
    assert not hasattr(puzzle, "puzzle_bytes")
    assert not hasattr(puzzle, "puzzle_sha256")


def test_parse_collection_semantics_fails_closed_on_missing_identity(tmp_path: Path):
    with pytest.raises(CorpusError, match="P999.*missing"):
        MoleculeDbAdapter().parse_collection_semantics(
            _collection(tmp_path, game_puzzle_id="P999"),
            puzzle_source=PUZZLE_SOURCE,
            molecules_source=MOLECULE_SOURCE,
        )