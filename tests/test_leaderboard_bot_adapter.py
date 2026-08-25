from __future__ import annotations

import io
from pathlib import Path

import pytest

from opus_corpus import github_source
from opus_corpus.adapters.leaderboard_bot import (
    LeaderboardBotAdapter,
    LeaderboardBotDataError,
)
from opus_corpus.cache import ContentAddressedCache
from opus_corpus.collections import CollectionDefinition, validate_collection

REPO_ROOT = Path(__file__).resolve().parents[1]
PUZZLE_PATH = "src/main/kotlin/com/faendir/zachtronics/bot/om/model/OmPuzzle.kt"
GROUP_PATH = "src/main/kotlin/com/faendir/zachtronics/bot/om/model/OmGroup.kt"
COLLECTION_PATH = "src/main/kotlin/com/faendir/zachtronics/bot/om/model/OmCollection.kt"
TYPE_PATH = "src/main/kotlin/com/faendir/zachtronics/bot/om/model/OmType.kt"
REQUIRED_PATHS = {PUZZLE_PATH, GROUP_PATH, COLLECTION_PATH, TYPE_PATH}

PUZZLES = b'''enum class OmPuzzle {
    STABILIZED_WATER(CHAPTER_1, NORMAL, "Stabilized Water", "P007"),
    SILVER_PAINT(CHAPTER_PRODUCTION, PRODUCTION, "Silver Paint", "P076"),
}
'''
GROUPS = b'''enum class OmGroup {
    CHAPTER_1(CAMPAIGN, "Chapter I"),
    CHAPTER_PRODUCTION(CAMPAIGN, "Appendix"),
}
'''
COLLECTIONS = b'''enum class OmCollection {
    CAMPAIGN("Campaign"),
}
'''
TYPES = b'''enum class OmType {
    NORMAL("normal"),
    PRODUCTION("production"),
}
'''


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
                "display_name": "Stabilized Water",
                "kind": "campaign",
                "group": "chapter-1",
                "game_puzzle_id": "P007",
                "leaderboard_key": "STABILIZED_WATER",
                "puzzle_type": "normal",
            },
            {
                "puzzle_id": "om.puzzle.0037",
                "display_name": "Silver Paint",
                "kind": "production",
                "group": "appendix",
                "game_puzzle_id": "P076",
                "leaderboard_key": "SILVER_PAINT",
                "puzzle_type": "production",
            },
        ),
        manifest={},
    )


def _source_members(*, puzzle_source: bytes = PUZZLES):
    payloads = {
        PUZZLE_PATH: puzzle_source,
        GROUP_PATH: GROUPS,
        COLLECTION_PATH: COLLECTIONS,
        TYPE_PATH: TYPES,
    }
    for path, payload in payloads.items():
        yield path, io.BytesIO(payload)


def test_fetch_caches_model_evidence_and_reconciles_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    def fake_members(owner: str, repo: str, revision: str):
        calls.append((owner, repo, revision))
        yield from _source_members()
        yield "README.md", _UnreadableStream()

    monkeypatch.setattr(github_source, "iter_github_tarball_members", fake_members)

    adapter = LeaderboardBotAdapter()
    cache_root = tmp_path / "cache"
    result = adapter.fetch(_collection(tmp_path), cache_root)

    assert calls == [
        (
            "F43nd1r",
            "zachtronics-leaderboard-bot",
            LeaderboardBotAdapter.pinned_revision,
        )
    ]
    assert result.source_id == "leaderboard-bot"
    assert result.candidate_count == 4
    assert result.puzzles_covered == 2

    receipts = list(
        ContentAddressedCache(cache_root).iter_receipts(
            "leaderboard-bot",
            LeaderboardBotAdapter.pinned_revision,
        )
    )
    assert {receipt.upstream_path for receipt in receipts} == REQUIRED_PATHS
    assert {receipt.rights_status for receipt in receipts} == {"local_fetch_only"}


def test_fetch_preserves_evidence_when_reconciliation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bad_puzzles = PUZZLES.replace(b"Stabilized Water", b"Wrong Name")
    monkeypatch.setattr(
        github_source,
        "iter_github_tarball_members",
        lambda *args: _source_members(puzzle_source=bad_puzzles),
    )
    cache_root = tmp_path / "cache"

    with pytest.raises(LeaderboardBotDataError, match="display_name"):
        LeaderboardBotAdapter().fetch(_collection(tmp_path), cache_root)

    receipts = list(
        ContentAddressedCache(cache_root).iter_receipts(
            "leaderboard-bot",
            LeaderboardBotAdapter.pinned_revision,
        )
    )
    assert len(receipts) == 4


def test_fetch_rejects_missing_required_model_before_cache_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def missing_type(*args):
        for path, member in _source_members():
            if path != TYPE_PATH:
                yield path, member

    monkeypatch.setattr(github_source, "iter_github_tarball_members", missing_type)
    cache_root = tmp_path / "cache"

    with pytest.raises(LeaderboardBotDataError, match="OmType.kt"):
        LeaderboardBotAdapter().fetch(_collection(tmp_path), cache_root)

    assert not cache_root.exists()


def test_reconciliation_rejects_duplicate_upstream_game_puzzle_id(tmp_path: Path):
    duplicate = PUZZLES.replace(b'"P076"', b'"P007"')

    with pytest.raises(LeaderboardBotDataError, match="duplicate game puzzle id"):
        LeaderboardBotAdapter().parse_collection_evidence(
            _collection(tmp_path),
            puzzle_source=duplicate,
            group_source=GROUPS,
            collection_source=COLLECTIONS,
            type_source=TYPES,
        )


@pytest.mark.upstream
def test_pinned_source_reconciles_frozen_base_game_collection():
    adapter = LeaderboardBotAdapter()
    files = {
        path: member.read()
        for path, member in github_source.iter_github_tarball_members(
            "F43nd1r",
            "zachtronics-leaderboard-bot",
            adapter.pinned_revision,
        )
        if path in REQUIRED_PATHS
    }
    assert set(files) == REQUIRED_PATHS

    collection = validate_collection(
        REPO_ROOT / "collections" / "base-game-2026-06-16.toml"
    )
    evidence = adapter.parse_collection_evidence(
        collection,
        puzzle_source=files[PUZZLE_PATH],
        group_source=files[GROUP_PATH],
        collection_source=files[COLLECTION_PATH],
        type_source=files[TYPE_PATH],
    )

    assert len(evidence) == collection.puzzle_count == 166
    assert tuple(item.game_puzzle_id for item in evidence) == tuple(
        row["game_puzzle_id"] for row in collection.inventory_rows
    )
    assert tuple(item.leaderboard_key for item in evidence) == tuple(
        row["leaderboard_key"] for row in collection.inventory_rows
    )


class _UnreadableStream:
    def read(self, *args, **kwargs):
        raise AssertionError("irrelevant archive members must not be read")
