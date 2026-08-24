from __future__ import annotations

import io
from pathlib import Path

from opus_corpus.adapters.base import AcquisitionResult
from opus_corpus.adapters.om_leaderboard import OmLeaderboardAdapter
from opus_corpus.collections import CollectionDefinition


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture-2026-08-24",
        inventory_sha256="0" * 64,
        puzzle_count=1,
        manifest_path=tmp_path / "fixture.toml",
        inventory_path=tmp_path / "fixture.csv",
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0092",
                "display_name": "Touchstone",
                "kind": "journal",
                "group": "journal-xcix-x",
                "game_puzzle_id": "P245",
                "leaderboard_key": "TOUCHSTONE",
                "puzzle_type": "normal",
            },
        ),
        manifest={},
    )


class _Unreadable(io.BytesIO):
    def read(self, *args, **kwargs):
        raise AssertionError("irrelevant archive member payload was read")


def test_leaderboard_filters_irrelevant_members_before_reading(monkeypatch, tmp_path: Path):
    def members(*args):
        yield "README.md", _Unreadable(b"large irrelevant payload")
        yield "JOURNAL_X/TOUCHSTONE/touchstone.solution", io.BytesIO(b"solution")

    monkeypatch.setattr(
        "opus_corpus.adapters.om_leaderboard.iter_github_tarball_members",
        members,
        raising=False,
    )
    monkeypatch.setattr(
        "opus_corpus.adapters.om_leaderboard.download_github_tarball",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("full tarball acquisition path was used")
        ),
        raising=False,
    )

    result = OmLeaderboardAdapter().fetch(_collection(tmp_path), tmp_path / "cache")

    assert result == AcquisitionResult(
        source_id="om-leaderboard",
        candidate_count=1,
        puzzles_covered=1,
    )
