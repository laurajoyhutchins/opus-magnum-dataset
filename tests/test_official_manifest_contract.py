from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.adapters.official_game import OfficialGameAcquisitionError, OfficialGameAdapter
from opus_corpus.cache import ContentAddressedCache
from opus_corpus.collections import CollectionDefinition
from opus_corpus.hashing import sha256_bytes
from opus_corpus.puzzle_materialization import (
    PuzzleMaterializationError,
    materialize_puzzle_artifacts,
)


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture",
        inventory_sha256="0" * 64,
        puzzle_count=1,
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
        ),
        manifest={},
    )


@pytest.mark.parametrize(
    "snapshot_id,manifest_body,include_puzzle",
    [
        (
            "fixture",
            '''schema_version = 1
snapshot_id = "fixture"
extra = "not allowed"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
''',
            True,
        ),
        (
            "../escape",
            '''schema_version = 1
snapshot_id = "../escape"
[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "P001.puzzle"
''',
            True,
        ),
        (
            "fixture",
            '''schema_version = 1
snapshot_id = "fixture"
puzzles = []
''',
            False,
        ),
    ],
)
def test_acquisition_and_materialization_share_manifest_rejections(
    tmp_path: Path,
    snapshot_id: str,
    manifest_body: str,
    include_puzzle: bool,
) -> None:
    collection = _collection(tmp_path)
    source_root = tmp_path / "official"
    source_root.mkdir()
    (source_root / "official-puzzles.toml").write_text(manifest_body, encoding="utf-8")
    if include_puzzle:
        (source_root / "P001.puzzle").write_bytes(b"puzzle bytes")

    with pytest.raises(OfficialGameAcquisitionError):
        OfficialGameAdapter(source_root).fetch(collection, tmp_path / "acquisition-cache")

    cache_root = tmp_path / "materialization-cache"
    cache = ContentAddressedCache(cache_root)
    revision = f"local-{sha256_bytes(snapshot_id.encode('utf-8'))}"
    cache.put_bytes(
        "official-game",
        revision,
        "official-puzzles.toml",
        manifest_body.encode("utf-8"),
        rights_status="local_fetch_only",
    )
    if include_puzzle:
        cache.put_bytes(
            "official-game",
            revision,
            "P001.puzzle",
            b"puzzle bytes",
            rights_status="local_fetch_only",
        )

    with pytest.raises(PuzzleMaterializationError):
        materialize_puzzle_artifacts(collection, cache_root)
