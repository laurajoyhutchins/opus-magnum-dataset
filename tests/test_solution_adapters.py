from __future__ import annotations

import json
from pathlib import Path

import pytest

from opus_corpus.adapters import (
    ADAPTERS,
    AdapterDataError,
    LeaderboardPuzzle,
    OmLeaderboardCandidate,
)


def _puzzle() -> LeaderboardPuzzle:
    return LeaderboardPuzzle(
        leaderboard_key="STABILIZED_WATER",
        group_key="CHAPTER_1",
        puzzle_type="normal",
        display_name="Stabilized Water",
        game_puzzle_id="P007",
        alt_ids=(),
    )


def _puzzle_dir(source_root: Path) -> Path:
    directory = source_root / "CHAPTER_1" / "STABILIZED_WATER"
    directory.mkdir(parents=True)
    return directory


def _write_metadata(path: Path, *, data_path: str | None = None) -> None:
    solution_path = path.with_suffix(".solution")
    path.write_text(
        json.dumps(
            {
                "puzzle": "STABILIZED_WATER",
                "score": {
                    "cost": 120,
                    "instructions": 67,
                    "cycles": 55,
                    "area": 11,
                },
                "displayLink": "https://example.invalid/display",
                "dataLink": "https://example.invalid/data",
                "dataPath": data_path
                or "CHAPTER_1/STABILIZED_WATER/120g_STABILIZED_WATER.solution",
                "lastModified": "2026-04-05T18:33:28Z",
            }
        ),
        encoding="utf-8",
    )
    solution_path.write_bytes(b"solution")


def test_om_archive_discovers_sorted_solution_paths(tmp_path: Path):
    source_root = tmp_path / "om-archive"
    directory = _puzzle_dir(source_root)
    (directory / "b_STABILIZED_WATER.solution").write_bytes(b"b")
    (directory / "a_STABILIZED_WATER.solution").write_bytes(b"a")
    (directory / "notes.txt").write_text("ignore", encoding="utf-8")

    paths = ADAPTERS["om-archive"]().solution_paths(source_root, _puzzle())

    assert tuple(path.name for path in paths) == (
        "a_STABILIZED_WATER.solution",
        "b_STABILIZED_WATER.solution",
    )


def test_om_archive_missing_puzzle_directory_has_no_candidates(tmp_path: Path):
    assert ADAPTERS["om-archive"]().solution_paths(tmp_path, _puzzle()) == ()


def test_om_leaderboard_pairs_solution_with_verified_metadata(tmp_path: Path):
    source_root = tmp_path / "om-leaderboard"
    directory = _puzzle_dir(source_root)
    metadata_path = directory / "120g_STABILIZED_WATER.json"
    _write_metadata(metadata_path)

    candidates = ADAPTERS["om-leaderboard"]().solution_candidates(
        source_root,
        _puzzle(),
    )

    assert candidates == (
        OmLeaderboardCandidate(
            solution_path=directory / "120g_STABILIZED_WATER.solution",
            metadata_path=metadata_path,
            claimed_cost=120,
            claimed_cycles=55,
            claimed_area=11,
            claimed_instructions=67,
            display_link="https://example.invalid/display",
            data_link="https://example.invalid/data",
            last_modified="2026-04-05T18:33:28Z",
        ),
    )


def test_om_leaderboard_allows_solution_without_adjacent_metadata(tmp_path: Path):
    source_root = tmp_path / "om-leaderboard"
    directory = _puzzle_dir(source_root)
    solution_path = directory / "raw_STABILIZED_WATER.solution"
    solution_path.write_bytes(b"solution")

    candidates = ADAPTERS["om-leaderboard"]().solution_candidates(
        source_root,
        _puzzle(),
    )

    assert candidates == (
        OmLeaderboardCandidate(
            solution_path=solution_path,
            metadata_path=None,
            claimed_cost=None,
            claimed_cycles=None,
            claimed_area=None,
            claimed_instructions=None,
            display_link=None,
            data_link=None,
            last_modified=None,
        ),
    )


def test_om_leaderboard_rejects_metadata_for_wrong_solution_path(tmp_path: Path):
    source_root = tmp_path / "om-leaderboard"
    directory = _puzzle_dir(source_root)
    metadata_path = directory / "120g_STABILIZED_WATER.json"
    _write_metadata(
        metadata_path,
        data_path="CHAPTER_1/STABILIZED_WATER/other.solution",
    )

    with pytest.raises(AdapterDataError, match="dataPath"):
        ADAPTERS["om-leaderboard"]().solution_candidates(source_root, _puzzle())
