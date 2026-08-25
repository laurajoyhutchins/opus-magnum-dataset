from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.adapters.molecule_db import MoleculeDbAdapter
from opus_corpus.cache import ContentAddressedCache
from opus_corpus.collections import CollectionDefinition
from opus_corpus.errors import CorpusError
from opus_corpus.molecule_db_evidence import materialize_molecule_db_semantic_evidence
from opus_corpus.observations import observation_id
from opus_corpus.puzzle_definition import reconcile_puzzle_definition

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
                        ty: BondType::Normal
                    }
                ]
            },
            vec![(Puzzle::AlphaPuzzle, 1, 1, None)]
        ),
    ]
}
'''


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="test-collection",
        inventory_sha256="0" * 64,
        puzzle_count=1,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0001",
                "display_name": "Alpha Puzzle",
                "kind": "campaign",
                "group": "chapter-1",
                "game_puzzle_id": "P001",
                "leaderboard_key": "P001",
                "puzzle_type": "normal",
            },
        ),
        manifest={},
    )


def _cache_sources(root: Path) -> None:
    cache = ContentAddressedCache(root)
    for path, payload in (
        ("src/puzzle.rs", PUZZLE_SOURCE),
        ("src/molecules.rs", MOLECULE_SOURCE),
    ):
        cache.put_bytes(
            MoleculeDbAdapter.source_id,
            MoleculeDbAdapter.pinned_revision,
            path,
            payload,
            rights_status="local_fetch_only",
        )


def test_materialized_molecule_db_evidence_links_joint_source_observations(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    _cache_sources(cache_root)

    result = materialize_molecule_db_semantic_evidence(_collection(tmp_path), cache_root)

    assert len(result.observations) == 2
    assert {row["source_path"] for row in result.observations} == {
        "src/puzzle.rs",
        "src/molecules.rs",
    }
    assert all(row["artifact_id"] is None for row in result.observations)
    assert all(row["source_role"] == "metadata" for row in result.observations)
    assert all(row["observed_sha256"] is None for row in result.observations)
    assert all(
        row["observation_id"]
        == observation_id({key: value for key, value in row.items() if key != "observation_id"})
        for row in result.observations
    )

    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert set(evidence.observation_ids) == {
        row["observation_id"] for row in result.observations
    }
    assert set(evidence.claims) == {"reagents", "products"}
    assert evidence.puzzle_artifact_id is None

    resolution = reconcile_puzzle_definition("om.puzzle.0001", result.evidence)
    assert resolution.definition is None
    assert set(resolution.source_observation_ids) == {
        row["observation_id"] for row in result.observations
    }
    assert "allowed_parts" in resolution.missing_fields
    assert "output_scale" in resolution.missing_fields


def test_materialization_fails_closed_when_one_pinned_source_file_is_missing(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    ContentAddressedCache(cache_root).put_bytes(
        MoleculeDbAdapter.source_id,
        MoleculeDbAdapter.pinned_revision,
        "src/puzzle.rs",
        PUZZLE_SOURCE,
        rights_status="local_fetch_only",
    )

    with pytest.raises(CorpusError, match="incomplete.*molecule-db"):
        materialize_molecule_db_semantic_evidence(_collection(tmp_path), cache_root)
