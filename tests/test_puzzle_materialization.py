from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.adapters.molecule_db import MoleculeDbAdapter
from opus_corpus.adapters.official_game import OfficialGameAdapter
from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.cache import ContentAddressedCache
from opus_corpus.collections import CollectionDefinition
from opus_corpus.content_store import ContentStoreError
from opus_corpus.hashing import sha256_bytes

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
                atoms: collect![HexIndex { q: 0, r: 0 } => Atom::Salt],
                bonds: collect![]
            },
            vec![(Puzzle::AlphaPuzzle, 1, 1, Some("Alpha Molecule")),]
        ),
    ]
}
'''


def _row(puzzle_id: str, game_puzzle_id: str, display_name: str) -> dict[str, str]:
    return {
        "puzzle_id": puzzle_id,
        "display_name": display_name,
        "kind": "campaign",
        "group": "chapter-1",
        "game_puzzle_id": game_puzzle_id,
        "leaderboard_key": display_name.upper().replace(" ", "_"),
        "puzzle_type": "normal",
    }


def _collection(tmp_path: Path) -> CollectionDefinition:
    row = _row("om.puzzle.0001", "P001", "Alpha Puzzle")
    return CollectionDefinition(
        collection_id="test-collection",
        inventory_sha256="0" * 64,
        puzzle_count=1,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=(row,),
        manifest={},
    )


def _two_puzzle_collection(tmp_path: Path) -> CollectionDefinition:
    rows = (
        _row("om.puzzle.0001", "P001", "Alpha Puzzle"),
        _row("om.puzzle.0002", "P002", "Beta Puzzle"),
    )
    return CollectionDefinition(
        collection_id="test-collection",
        inventory_sha256="0" * 64,
        puzzle_count=2,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=rows,
        manifest={},
    )


def _cache_identical_exact_sources(cache_root: Path, *, official_first: bool) -> None:
    cache = ContentAddressedCache(cache_root)
    puzzle_bytes = b"same exact puzzle bytes"
    snapshot_id = "fixture-snapshot"
    official_revision = f"local-{sha256_bytes(snapshot_id.encode('utf-8'))}"
    manifest_bytes = b'''\
schema_version = 1
snapshot_id = "fixture-snapshot"

[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "official/P001.puzzle"
'''

    def put_omsim() -> None:
        cache.put_bytes(
            "omsim",
            OmsimAdapter.pinned_revision,
            "test/puzzle/campaign/P001.puzzle",
            puzzle_bytes,
            rights_status="local_fetch_only",
        )

    def put_official() -> None:
        cache.put_bytes(
            "official-game",
            official_revision,
            "official-puzzles.toml",
            manifest_bytes,
            rights_status="local_fetch_only",
        )
        cache.put_bytes(
            "official-game",
            official_revision,
            "official/P001.puzzle",
            puzzle_bytes,
            rights_status="local_fetch_only",
        )

    if official_first:
        put_official()
        put_omsim()
    else:
        put_omsim()
        put_official()


def _cache_divergent_exact_sources(cache_root: Path) -> None:
    cache = ContentAddressedCache(cache_root)
    snapshot_id = "fixture-snapshot"
    official_revision = f"local-{sha256_bytes(snapshot_id.encode('utf-8'))}"
    manifest_bytes = b'''\
schema_version = 1
snapshot_id = "fixture-snapshot"

[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "official/P001.puzzle"
'''
    cache.put_bytes(
        "omsim",
        OmsimAdapter.pinned_revision,
        "test/puzzle/campaign/P001.puzzle",
        b"omsim puzzle bytes",
        rights_status="local_fetch_only",
    )
    cache.put_bytes(
        "official-game",
        official_revision,
        "official-puzzles.toml",
        manifest_bytes,
        rights_status="local_fetch_only",
    )
    cache.put_bytes(
        "official-game",
        official_revision,
        "official/P001.puzzle",
        b"different official puzzle bytes",
        rights_status="local_fetch_only",
    )


def test_omsim_receipt_materializes_canonical_puzzle_artifact(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    cache_root = tmp_path / "cache"
    cache = ContentAddressedCache(cache_root)
    receipt = cache.put_bytes(
        "omsim",
        OmsimAdapter.pinned_revision,
        "test/puzzle/campaign/P001.puzzle",
        b"exact puzzle bytes",
        rights_status="local_fetch_only",
    )

    result = materialize_puzzle_artifacts(_collection(tmp_path), cache_root)

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_kind == "puzzle"
    assert artifact.artifact_id == f"om.puzzle-artifact.sha256.{receipt.sha256}"
    assert artifact.puzzle_id == "om.puzzle.0001"
    assert artifact.artifact_format == "puzzle"
    assert artifact.rights_status == "local_fetch_only"
    assert {row.source_id for row in result.provenance} == {"omsim"}

    assert len(result.coverage) == 1
    coverage = result.coverage[0]
    assert coverage.puzzle_id == "om.puzzle.0001"
    assert coverage.puzzle_definition_id is None
    assert coverage.artifact_ids == (artifact.artifact_id,)
    assert coverage.exact_source_ids == ("omsim",)
    assert coverage.semantic_source_ids == ()
    assert coverage.semantic_covered is False
    assert coverage.artifact_covered is True
    assert coverage.verifier_ready is True


def test_identical_official_and_omsim_bytes_share_one_artifact(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    cache_root = tmp_path / "cache"
    _cache_identical_exact_sources(cache_root, official_first=False)

    result = materialize_puzzle_artifacts(_collection(tmp_path), cache_root)

    assert len(result.artifacts) == 1
    assert {row.source_id for row in result.provenance} == {"official-game", "omsim"}
    coverage = result.coverage[0]
    assert coverage.exact_source_ids == ("official-game", "omsim")
    assert coverage.artifact_ids == (result.artifacts[0].artifact_id,)
    assert coverage.artifact_covered is True
    assert coverage.verifier_ready is True


def test_official_manifest_mapping_is_preserved_as_artifact_evidence(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    cache_root = tmp_path / "cache"
    cache = ContentAddressedCache(cache_root)
    snapshot_id = "fixture-snapshot"
    revision = f"local-{sha256_bytes(snapshot_id.encode('utf-8'))}"
    manifest_receipt = cache.put_bytes(
        "official-game",
        revision,
        "official-puzzles.toml",
        b'''\
schema_version = 1
snapshot_id = "fixture-snapshot"

[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "official/P001.puzzle"
''',
        rights_status="local_fetch_only",
    )
    puzzle_receipt = cache.put_bytes(
        "official-game",
        revision,
        "official/P001.puzzle",
        b"official puzzle bytes",
        rights_status="local_fetch_only",
    )

    result = materialize_puzzle_artifacts(_collection(tmp_path), cache_root)

    artifact_id = f"om.puzzle-artifact.sha256.{puzzle_receipt.sha256}"
    rows = [row for row in result.provenance if row.source_id == "official-game"]
    assert len(rows) == 2

    artifact_row = next(row for row in rows if row.source_role == "artifact")
    assert artifact_row.artifact_id == artifact_id
    assert artifact_row.source_path == "official/P001.puzzle"
    assert artifact_row.observed_sha256 == puzzle_receipt.sha256

    evidence_row = next(row for row in rows if row.source_role == "evidence")
    assert evidence_row.artifact_id == artifact_id
    assert evidence_row.source_path == "official-puzzles.toml"
    assert evidence_row.source_object_id == "om.puzzle.0001"
    assert evidence_row.source_evidence_sha256 == manifest_receipt.sha256


def test_official_acquisition_output_materializes_with_same_manifest_contract(
    tmp_path: Path,
) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    source_root = tmp_path / "official"
    cache_root = tmp_path / "cache"
    source_root.mkdir()
    (source_root / "official-puzzles.toml").write_text(
        '''schema_version = 1
snapshot_id = "fixture-snapshot"

[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "campaign//P001.puzzle"
''',
        encoding="utf-8",
    )
    (source_root / "campaign").mkdir()
    (source_root / "campaign/P001.puzzle").write_bytes(b"official puzzle bytes")

    OfficialGameAdapter(source_root).fetch(_collection(tmp_path), cache_root)
    result = materialize_puzzle_artifacts(_collection(tmp_path), cache_root)

    assert len(result.artifacts) == 1
    artifact_row = next(row for row in result.provenance if row.source_role == "artifact")
    assert artifact_row.source_path == "campaign/P001.puzzle"
    evidence_row = next(row for row in result.provenance if row.source_role == "evidence")
    assert evidence_row.source_path == "official-puzzles.toml"


def test_divergent_exact_bytes_are_preserved_but_not_verifier_ready(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    cache_root = tmp_path / "cache"
    _cache_divergent_exact_sources(cache_root)

    result = materialize_puzzle_artifacts(_collection(tmp_path), cache_root)

    assert len(result.artifacts) == 2
    coverage = result.coverage[0]
    assert len(coverage.artifact_ids) == 2
    assert coverage.artifact_covered is True
    assert coverage.verifier_ready is False
    assert coverage.exact_source_ids == ("official-game", "omsim")


def test_molecule_db_semantics_do_not_substitute_for_exact_puzzle_bytes(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    cache_root = tmp_path / "cache"
    cache = ContentAddressedCache(cache_root)
    cache.put_bytes(
        "molecule-db",
        MoleculeDbAdapter.pinned_revision,
        "src/puzzle.rs",
        PUZZLE_SOURCE,
        rights_status="local_fetch_only",
    )
    cache.put_bytes(
        "molecule-db",
        MoleculeDbAdapter.pinned_revision,
        "src/molecules.rs",
        MOLECULE_SOURCE,
        rights_status="local_fetch_only",
    )

    result = materialize_puzzle_artifacts(_collection(tmp_path), cache_root)

    assert result.artifacts == ()
    assert result.provenance == ()
    coverage = result.coverage[0]
    assert coverage.artifact_ids == ()
    assert coverage.exact_source_ids == ()
    assert coverage.semantic_source_ids == ()
    assert coverage.semantic_covered is False
    assert coverage.artifact_covered is False
    assert coverage.verifier_ready is False


def test_complete_coverage_assertion_names_missing_or_ambiguous_puzzles(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import (
        PuzzleCoverageError,
        materialize_puzzle_artifacts,
        require_complete_puzzle_coverage,
    )

    cache_root = tmp_path / "cache"
    cache = ContentAddressedCache(cache_root)
    cache.put_bytes(
        "omsim",
        OmsimAdapter.pinned_revision,
        "test/puzzle/campaign/P001.puzzle",
        b"alpha puzzle bytes",
        rights_status="local_fetch_only",
    )

    incomplete = materialize_puzzle_artifacts(_two_puzzle_collection(tmp_path), cache_root)
    with pytest.raises(PuzzleCoverageError, match=r"om\.puzzle\.0002"):
        require_complete_puzzle_coverage(incomplete)

    cache.put_bytes(
        "omsim",
        OmsimAdapter.pinned_revision,
        "test/puzzle/campaign/P002.puzzle",
        b"beta puzzle bytes",
        rights_status="local_fetch_only",
    )
    complete = materialize_puzzle_artifacts(_two_puzzle_collection(tmp_path), cache_root)
    require_complete_puzzle_coverage(complete)


def test_corrupt_exact_puzzle_object_fails_closed(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    cache_root = tmp_path / "cache"
    cache = ContentAddressedCache(cache_root)
    receipt = cache.put_bytes(
        "omsim",
        OmsimAdapter.pinned_revision,
        "test/puzzle/campaign/P001.puzzle",
        b"exact puzzle bytes",
        rights_status="local_fetch_only",
    )
    cache.store.object_path(receipt.sha256).write_bytes(b"corrupt")

    with pytest.raises(ContentStoreError, match="byte length mismatch|corrupt content object"):
        materialize_puzzle_artifacts(_collection(tmp_path), cache_root)


def test_artifact_and_coverage_output_ignore_source_insertion_order(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifacts

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _cache_identical_exact_sources(first_root, official_first=False)
    _cache_identical_exact_sources(second_root, official_first=True)

    first = materialize_puzzle_artifacts(_collection(tmp_path), first_root)
    second = materialize_puzzle_artifacts(_collection(tmp_path), second_root)

    assert first.artifacts == second.artifacts
    assert first.coverage == second.coverage
