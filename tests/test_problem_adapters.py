from pathlib import Path

import pytest

from opus_corpus.adapters import ADAPTERS, AdapterDataError, LeaderboardPuzzle


def _puzzle() -> LeaderboardPuzzle:
    return LeaderboardPuzzle(
        leaderboard_key="STABILIZED_WATER",
        group_key="CHAPTER_1",
        puzzle_type="normal",
        display_name="Stabilized Water",
        game_puzzle_id="P007",
        alt_ids=(),
    )


def test_omsim_finds_fixture_by_upstream_game_id(tmp_path: Path):
    source_root = tmp_path / "omsim"
    expected = source_root / "test/puzzle/campaign/ch1-and-prologue/P007.puzzle"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"puzzle")
    (expected.parent / "P008.puzzle").write_bytes(b"other")

    assert ADAPTERS["omsim"]().puzzle_path(source_root, _puzzle()) == expected


def test_omsim_missing_fixture_returns_none(tmp_path: Path):
    assert ADAPTERS["omsim"]().puzzle_path(tmp_path, _puzzle()) is None


def test_omsim_duplicate_fixture_fails_closed(tmp_path: Path):
    source_root = tmp_path / "omsim"
    for directory in ("test/puzzle/a", "test/puzzle/b"):
        path = source_root / directory / "P007.puzzle"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"puzzle")

    with pytest.raises(AdapterDataError, match="multiple fixtures"):
        ADAPTERS["omsim"]().puzzle_path(source_root, _puzzle())
