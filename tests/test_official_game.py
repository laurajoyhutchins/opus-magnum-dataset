from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from opus_corpus.adapters.official_game import OfficialGameAcquisitionError, OfficialGameAdapter
from opus_corpus.cache import ContentAddressedCache
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


def _only_revision(cache_root: Path) -> str:
    revision_root = cache_root / "receipts" / "official-game"
    revisions = sorted(path.name for path in revision_root.iterdir() if path.is_dir())
    assert len(revisions) == 1
    return revisions[0]


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
    revision = _only_revision(cache_root)
    receipt_path = cache.receipt_path(
        "official-game", revision, "campaign/P001.puzzle"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["rights_status"] == "local_fetch_only"
    assert cache.object_path(receipt["sha256"]).read_bytes() == b"puzzle-one\x00"


def test_fetch_caches_exact_manifest_as_source_fact(tmp_path: Path):
    source_root = tmp_path / "official"
    cache_root = tmp_path / "cache"
    manifest_body = '''schema_version = 1
snapshot_id = "fixture-build"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
'''
    _write_manifest(source_root, manifest_body)
    (source_root / "P001.puzzle").write_bytes(b"one")

    OfficialGameAdapter(source_root).fetch(_collection(tmp_path), cache_root)

    cache = ContentAddressedCache(cache_root)
    revision = _only_revision(cache_root)
    receipt_path = cache.receipt_path(
        "official-game", revision, "official-puzzles.toml"
    )
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["rights_status"] == "local_fetch_only"
    assert cache.object_path(receipt["sha256"]).read_bytes() == manifest_body.encode("utf-8")


def test_fetch_uses_filesystem_safe_revision(tmp_path: Path):
    source_root = tmp_path / "official"
    cache_root = tmp_path / "cache"
    _write_manifest(
        source_root,
        '''schema_version = 1
snapshot_id = "fixture-build."
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
''',
    )
    (source_root / "P001.puzzle").write_bytes(b"one")

    OfficialGameAdapter(source_root).fetch(_collection(tmp_path), cache_root)

    revision = _only_revision(cache_root)
    assert re.fullmatch(r"[A-Za-z0-9._-]+", revision)
    assert not revision.endswith(".")


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
        revision = _only_revision(cache_root)
        receipt_path = cache.receipt_path(
            "official-game", revision, "P001.puzzle"
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


def test_same_label_changed_bytes_produce_new_immutable_source_revision(tmp_path: Path):
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
    path = source_root / "P001.puzzle"
    path.write_bytes(b"first")
    adapter = OfficialGameAdapter(source_root)
    adapter.fetch(_collection(tmp_path), cache_root)
    revision_first = _only_revision(cache_root)

    path.write_bytes(b"changed")
    adapter.fetch(_collection(tmp_path), cache_root)
    revisions = {p.name for p in (cache_root / "receipts" / "official-game").iterdir()}
    assert len(revisions) == 2
    assert revision_first in revisions
    revision_second = (revisions - {revision_first}).pop()
    assert revision_first != revision_second
    cache = ContentAddressedCache(cache_root)
    for revision, expected in ((revision_first, b"first"), (revision_second, b"changed")):
        receipt = json.loads(
            cache.receipt_path("official-game", revision, "P001.puzzle").read_text()
        )
        assert cache.object_path(receipt["sha256"]).read_bytes() == expected


def test_same_label_remapped_manifest_produces_new_revision(tmp_path: Path):
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
    (source_root / "P001.puzzle").write_bytes(b"same bytes")
    adapter = OfficialGameAdapter(source_root)
    adapter.fetch(_collection(tmp_path), cache_root)
    before = _only_revision(cache_root)

    _write_manifest(
        source_root,
        '''schema_version = 1
snapshot_id = "fixture"
[[puzzles]]
puzzle_id = "om.puzzle.0002"
path = "P001.puzzle"
''',
    )
    adapter.fetch(_collection(tmp_path), cache_root)
    revisions = {p.name for p in (cache_root / "receipts" / "official-game").iterdir()}
    assert len(revisions) == 2
    assert before in revisions


def test_independent_cache_revisions_commit_to_bytes_not_snapshot_label_alone(
    tmp_path: Path,
):
    manifest = '''schema_version = 1
snapshot_id = "same-label"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
'''
    revisions = []
    for side, content in (("first", b"left"), ("second", b"right")):
        source = tmp_path / side / "source"
        cache_root = tmp_path / side / "cache"
        _write_manifest(source, manifest)
        (source / "P001.puzzle").write_bytes(content)
        OfficialGameAdapter(source).fetch(_collection(tmp_path), cache_root)
        revisions.append(_only_revision(cache_root))
    assert revisions[0] != revisions[1]


def test_semantically_reordered_manifest_uses_the_same_source_revision(tmp_path: Path):
    manifest_a = '''schema_version = 1
snapshot_id = "same-label"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
[[puzzles]]
puzzle_id = "om.puzzle.0002"
path = "P002.puzzle"
'''
    manifest_b = '''snapshot_id = "same-label"
schema_version = 1
[[puzzles]]
path = "P002.puzzle"
puzzle_id = "om.puzzle.0002"
[[puzzles]]
path = "P001.puzzle"
puzzle_id = "om.puzzle.0001"
'''
    revisions = []
    for side, manifest in (("left", manifest_a), ("right", manifest_b)):
        source = tmp_path / side / "source"
        cache_root = tmp_path / side / "cache"
        _write_manifest(source, manifest)
        (source / "P001.puzzle").write_bytes(b"one")
        (source / "P002.puzzle").write_bytes(b"two")
        OfficialGameAdapter(source).fetch(_collection(tmp_path), cache_root)
        revisions.append(_only_revision(cache_root))
    assert revisions[0] == revisions[1]
