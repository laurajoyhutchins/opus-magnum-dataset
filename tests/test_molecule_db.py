from __future__ import annotations

import io
import json
import tarfile
from hashlib import sha256
from pathlib import Path

import pytest

from opus_corpus import github_source
from opus_corpus.adapters.molecule_db import MoleculeDbAdapter
from opus_corpus.collections import CollectionDefinition, validate_collection
from opus_corpus.errors import CorpusError

REPO_ROOT = Path(__file__).resolve().parents[1]

PUZZLE_SOURCE = b'''\
puzzles! {
    AlphaPuzzle => "Alpha Puzzle", official(Campaign(1), "P001"),
}
'''
MOLECULE_SOURCE = b'''\
pub(crate) fn molecules() -> Vec<()> {
    vec![
        (
            Molecule {
                atoms: collect![
                    HexIndex { q: 0, r: 0 } => Atom::Salt,
                    HexIndex { q: 1, r: 0 } => Atom::Fire
                ],
                bonds: collect![
                    Bond {
                        start: HexIndex { q: 0, r: 0 },
                        end: HexIndex { q: 1, r: 0 },
                        ty: BondType::Triplex {
                            red: true,
                            black: false,
                            yellow: true
                        }
                    }
                ]
            },
            vec![
                (Puzzle::AlphaPuzzle, 1, 1, Some("Alpha Molecule")),
            ]
        ),
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


def _mock_tarball(monkeypatch, payload: bytes) -> None:
    monkeypatch.setattr(
        github_source,
        "iter_github_tarball_members",
        lambda *args: github_source.iter_tarball_members(io.BytesIO(payload)),
    )


def test_fetch_caches_only_semantic_source_files_with_provenance(monkeypatch, tmp_path: Path):
    payload = _tarball(
        {
            "src/puzzle.rs": PUZZLE_SOURCE,
            "src/molecules.rs": MOLECULE_SOURCE,
            "README.md": b"not semantic evidence",
        }
    )
    _mock_tarball(monkeypatch, payload)

    result = MoleculeDbAdapter().fetch(_collection(tmp_path), tmp_path / "cache")

    assert result.candidate_count == 2
    assert result.puzzles_covered == 1
    receipts = sorted((tmp_path / "cache" / "receipts" / "molecule-db").rglob("*.json"))
    assert len(receipts) == 2
    observed = [json.loads(path.read_text()) for path in receipts]
    assert {item["upstream_path"] for item in observed} == {"src/puzzle.rs", "src/molecules.rs"}
    assert {item["revision"] for item in observed} == {MoleculeDbAdapter.pinned_revision}
    assert {item["rights_status"] for item in observed} == {"local_fetch_only"}


def test_fetch_caches_semantic_source_files_before_reconciliation_failure(
    monkeypatch, tmp_path: Path
):
    payload = _tarball(
        {
            "src/puzzle.rs": PUZZLE_SOURCE,
            "src/molecules.rs": MOLECULE_SOURCE,
        }
    )
    _mock_tarball(monkeypatch, payload)
    cache_root = tmp_path / "cache"

    with pytest.raises(CorpusError, match="P999.*missing"):
        MoleculeDbAdapter().fetch(_collection(tmp_path, game_puzzle_id="P999"), cache_root)

    receipts = sorted((cache_root / "receipts" / "molecule-db").rglob("*.json"))
    assert len(receipts) == 2
    observed = [json.loads(path.read_text()) for path in receipts]
    assert {item["upstream_path"] for item in observed} == {"src/puzzle.rs", "src/molecules.rs"}


@pytest.mark.upstream
def test_pinned_source_reconciles_frozen_base_game_collection():
    adapter = MoleculeDbAdapter()
    files = {
        path: member.read()
        for path, member in github_source.iter_github_tarball_members(
            "fenhl",
            "molecule-db",
            adapter.pinned_revision,
        )
        if path in {"src/molecules.rs", "src/puzzle.rs"}
    }
    observed_hashes = {
        path: sha256(files[path]).hexdigest()
        for path in ("src/molecules.rs", "src/puzzle.rs")
    }
    assert observed_hashes == {
        "src/molecules.rs": "09dbca0f67ba16178f98da0f2a94f642e3114f61a0a3d79c434d8411df175a58",
        "src/puzzle.rs": "d6fd2f8d99731081f5d76ab47fbd67c2c19f02f73e04cdb1bdd1ad4534096f11",
    }

    collection = validate_collection(REPO_ROOT / "collections" / "base-game-2026-06-16.toml")
    semantics = adapter.parse_collection_semantics(
        collection,
        puzzle_source=files["src/puzzle.rs"],
        molecules_source=files["src/molecules.rs"],
    )

    assert len(semantics) == collection.puzzle_count == 166
    assert tuple(item.game_puzzle_id for item in semantics) == tuple(
        row["game_puzzle_id"] for row in collection.inventory_rows
    )


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
    ] == [
        (0, 0, 1, 0, "Triplex { red: true, black: false, yellow: true }"),
    ]
    assert not hasattr(puzzle, "puzzle_bytes")
    assert not hasattr(puzzle, "puzzle_sha256")


def test_parse_collection_semantics_fails_closed_on_missing_identity(tmp_path: Path):
    with pytest.raises(CorpusError, match="P999.*missing"):
        MoleculeDbAdapter().parse_collection_semantics(
            _collection(tmp_path, game_puzzle_id="P999"),
            puzzle_source=PUZZLE_SOURCE,
            molecules_source=MOLECULE_SOURCE,
        )
