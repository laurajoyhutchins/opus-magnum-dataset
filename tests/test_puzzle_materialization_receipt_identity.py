from __future__ import annotations

import json
from pathlib import Path

import pytest

from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.cache import ContentAddressedCache
from opus_corpus.collections import CollectionDefinition


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
                "leaderboard_key": "ALPHA_PUZZLE",
                "puzzle_type": "normal",
            },
        ),
        manifest={},
    )


def test_materialization_rejects_receipt_moved_to_different_embedded_path(
    tmp_path: Path,
) -> None:
    from opus_corpus.puzzle_materialization import (
        PuzzleMaterializationError,
        materialize_puzzle_artifacts,
    )

    cache_root = tmp_path / "cache"
    cache = ContentAddressedCache(cache_root)
    original_path = "test/puzzle/campaign/P001.puzzle"
    receipt = cache.put_bytes(
        "omsim",
        OmsimAdapter.pinned_revision,
        original_path,
        b"exact puzzle bytes",
        rights_status="local_fetch_only",
    )
    receipt_path = cache.receipt_path(
        receipt.source_id,
        receipt.revision,
        receipt.upstream_path,
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["upstream_path"] = "test/puzzle/campaign/P002.puzzle"
    receipt_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PuzzleMaterializationError, match="receipt path does not match identity"):
        materialize_puzzle_artifacts(_collection(tmp_path), cache_root)
