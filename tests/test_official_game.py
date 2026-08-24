from __future__ import annotations

import json
from pathlib import Path

import pytest

from opus_corpus.adapters.official_game import OfficialGameAcquisitionError, OfficialGameAdapter
from opus_corpus.cache import CacheIntegrityError, ContentAddressedCache
from opus_corpus.collections import CollectionDefinition


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture",
        inventory_sha256="0" * 64,
        puzzle_count=2,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0001",
                "display_name": "One",
                "kind": "campaign",
                "group": "chapter-1",
                "game_puzzle_id": "P001",
                "leaderboard_key": "ONE",
                "puzzle_type": "normal",
            },
            {
                "puzzle_id": "om.puzzle.0002",
                "display_name": "Two",
                "kind": "campaign",
                "group": "chapter-1",
                "game_puzzle_id": "P002",
                "leaderboard_key": "TWO",
                "puzzle_type": "normal",
            },
        ),
        manifest={},
    )


def _write_manifest(root: Path, body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "official-puzzles.toml").write_text(body, encoding="utf-8")


def test_fetch_caches_exact_local_puzzle_bytes_with_provenance(tmp_path: Path):
    source_root = tmp_path / "official"
    cache_root = tmp_path / "cache"
    _write_manifest(
        source_root,
        '''schema_version = 1
snapshot_id = "fixture-build"

[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "campaign/P001.puzzle"

[[puzzles]]
puzzle_id = "om.puzzle.0002"
path = "campaign/P002.puzzle"
''',
    )
    (source_root / "campaign").mkdir()
    (source_root / "campaign/P001.puzzle").write_bytes(b"puzzle-one\x00")
    (source_root / "campaign/P002.puzzle").write_bytes(b"puzzle-two\x00")

    result = OfficialGameAdapter(source_root).fetch(_collection(tmp_path), cache_root)

    assert result.source_id == "official-game"
    assert result.candidate_count == 2
    assert result.puzzles_covered == 2

    cache = ContentAddressedCache(cache_root)
    receipt_path = cache.receipt_path(
        "official-game", "local:fixture-build", "campaign/P001.puzzle"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["rights_status"] == "local_fetch_only"
    assert cache.object_path(receipt["sha256"]).read_bytes() == b"puzzle-one\x00"


def test_fetch_uses_relative_provenance_independent_of_local_root(tmp_path: Path):
    manifests = '''schema_version = 1
snapshot_id = "same-snapshot"

[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
'''
    receipts = []
    for name in ("left", "right"):
        source_root = tmp_path / name / "official"
        cache_root = tmp_path / name / "cache"
        _write_manifest(source_root, manifests)
        (source_root / "P001.puzzle").write_bytes(b"same exact bytes")
        OfficialGameAdapter(source_root).fetch(_collection(tmp_path), cache_root)
        cache = ContentAddressedCache(cache_root)
        receipt_path = cache.receipt_path(
            "official-game", "local:same-snapshot", "P001.puzzle"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipts.append((receipt_path.relative_to(cache_root), receipt["sha256"]))

    assert receipts[0] == receipts[1]


def test_fetch_rejects_snapshot_id_that_can_escape_receipt_path(tmp_path: Path):
    source_root = tmp_path / "official"
    _write_manifest(
        source_root,
        '''schema_version = 1
snapshot_id = "../escape"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
''',
    )
    (source_root / "P001.puzzle").write_bytes(b"one")

    with pytest.raises(OfficialGameAcquisitionError, match="snapshot_id"):
        OfficialGameAdapter(source_root).fetch(_collection(tmp_path), tmp_path / "cache")


@pytest.mark.parametrize(
    "body,match",
    [
        (
            '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "copy/P001.puzzle"
''',
            "duplicate puzzle_id",
        ),
        (
            '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "shared.puzzle"
[[puzzles]]
puzzle_id = "om.puzzle.0002"
path = "shared.puzzle"
''',
            "duplicate path",
        ),
        (
            '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.9999"
path = "P999.puzzle"
''',
            "not in collection",
        ),
        (
            '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "../P001.puzzle"
''',
            "relative .puzzle path",
        ),
    ],
)
def test_fetch_rejects_ambiguous_or_unsafe_manifest(
    tmp_path: Path, body: str, match: str
):
    source_root = tmp_path / "official"
    _write_manifest(source_root, body)
    (source_root / "P001.puzzle").write_bytes(b"one")
    (source_root / "shared.puzzle").write_bytes(b"shared")

    with pytest.raises(OfficialGameAcquisitionError, match=match):
        OfficialGameAdapter(source_root).fetch(_collection(tmp_path), tmp_path / "cache")


def test_fetch_rejects_missing_explicit_puzzle_file(tmp_path: Path):
    source_root = tmp_path / "official"
    _write_manifest(
        source_root,
        '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
''',
    )

    with pytest.raises(OfficialGameAcquisitionError, match="missing puzzle file"):
        OfficialGameAdapter(source_root).fetch(_collection(tmp_path), tmp_path / "cache")


def test_fetch_rejects_mutation_within_same_local_snapshot(tmp_path: Path):
    source_root = tmp_path / "official"
    cache_root = tmp_path / "cache"
    _write_manifest(
        source_root,
        '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
''',
    )
    puzzle_path = source_root / "P001.puzzle"
    puzzle_path.write_bytes(b"first")
    adapter = OfficialGameAdapter(source_root)
    adapter.fetch(_collection(tmp_path), cache_root)

    puzzle_path.write_bytes(b"changed")
    with pytest.raises(CacheIntegrityError, match="pinned source path changed"):
        adapter.fetch(_collection(tmp_path), cache_root)


def test_invalid_manifest_does_not_partially_mutate_cache(tmp_path: Path):
    source_root = tmp_path / "official"
    cache_root = tmp_path / "cache"
    _write_manifest(
        source_root,
        '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "copy/P001.puzzle"
''',
    )
    (source_root / "P001.puzzle").write_bytes(b"one")
    (source_root / "copy").mkdir()
    (source_root / "copy/P001.puzzle").write_bytes(b"duplicate")

    with pytest.raises(OfficialGameAcquisitionError, match="duplicate puzzle_id"):
        OfficialGameAdapter(source_root).fetch(_collection(tmp_path), cache_root)

    assert not cache_root.exists()
