from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from opus_corpus.adapters.base import AcquisitionResult
from opus_corpus.adapters.om_leaderboard import OmLeaderboardAdapter
from opus_corpus.collections import CollectionDefinition, validate_collection


def fixture_collection() -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture-2026-08-24",
        inventory_sha256="0" * 64,
        puzzle_count=3,
        manifest_path=Path("fixture.toml"),
        inventory_path=Path("fixture.csv"),
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
                "puzzle_id": "om.puzzle.0092",
                "display_name": "Touchstone",
                "kind": "journal",
                "group": "journal-xcix-x",
                "game_puzzle_id": "P245",
                "leaderboard_key": "TOUCHSTONE",
                "puzzle_type": "normal",
            },
            {
                "puzzle_id": "om.puzzle.0107",
                "display_name": "Lodestone",
                "kind": "journal",
                "group": "journal-cviii-i",
                "game_puzzle_id": "P256",
                "leaderboard_key": "LODESTONE",
                "puzzle_type": "normal",
            },
        ),
        manifest={},
    )


def make_tarball(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, payload in files.items():
            info = tarfile.TarInfo(name=f"om-leaderboard-fixture/{path}")
            info.size = len(payload)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_expected_directories_cover_all_collection_puzzles():
    root = Path(__file__).resolve().parents[1]
    collection = validate_collection(root / "collections/base-game-2026-06-16.toml")

    directories = OmLeaderboardAdapter._expected_directories(collection)

    assert len(directories) == 166
    assert directories["CHAPTER_1/STABILIZED_WATER"] == "om.puzzle.0001"
    assert directories["JOURNAL_X/TOUCHSTONE"] == "om.puzzle.0092"
    assert directories["JOURNAL_CVIII_XII/GUIPURE_LACE"] == "om.puzzle.0166"


def test_fetch_preserves_all_collection_matching_source_facts(tmp_path, monkeypatch):
    touchstone_json = json.dumps(
        {"cost": 125, "cycles": 113, "dataPath": "touchstone.solution"}
    ).encode()
    lodestone_json = json.dumps(
        {"cost": 200, "cycles": 90, "dataPath": "lodestone.solution"}
    ).encode()
    orphan_json = json.dumps(
        {"cost": 1, "cycles": 1, "dataPath": "missing.solution"}
    ).encode()
    tarball = make_tarball(
        {
            "JOURNAL_X/TOUCHSTONE/touchstone.solution": b"touchstone-solution",
            "JOURNAL_X/TOUCHSTONE/touchstone.json": touchstone_json,
            "JOURNAL_X/TOUCHSTONE/orphan.json": orphan_json,
            "JOURNAL_CVIII_I/LODESTONE/lodestone.solution": b"lodestone-solution",
            "JOURNAL_CVIII_I/LODESTONE/lodestone.json": lodestone_json,
            "CHAPTER_1/STABILIZED_WATER/campaign.solution": b"campaign-solution",
            "JOURNAL_X/OTHER/other.solution": b"other-puzzle",
        }
    )
    monkeypatch.setattr(
        "opus_corpus.adapters.om_leaderboard.download_github_tarball",
        lambda owner, repo, revision: tarball,
    )

    result = OmLeaderboardAdapter().fetch(fixture_collection(), tmp_path)

    assert result == AcquisitionResult(
        source_id="om-leaderboard",
        candidate_count=3,
        puzzles_covered=3,
    )
    receipts = sorted((tmp_path / "receipts" / "om-leaderboard").rglob("*.json"))
    assert len(receipts) == 6
    objects = sorted((tmp_path / "objects" / "sha256").rglob("*"))
    assert {path.read_bytes() for path in objects if path.is_file()} == {
        b"touchstone-solution",
        b"lodestone-solution",
        b"campaign-solution",
        touchstone_json,
        lodestone_json,
        orphan_json,
    }


def test_repeated_fetch_is_idempotent(tmp_path, monkeypatch):
    tarball = make_tarball(
        {
            "JOURNAL_X/TOUCHSTONE/touchstone.solution": b"touchstone-solution",
            "JOURNAL_X/TOUCHSTONE/touchstone.json": b"{}",
        }
    )
    monkeypatch.setattr(
        "opus_corpus.adapters.om_leaderboard.download_github_tarball",
        lambda owner, repo, revision: tarball,
    )
    adapter = OmLeaderboardAdapter()

    first = adapter.fetch(fixture_collection(), tmp_path)
    receipt_paths = sorted((tmp_path / "receipts" / "om-leaderboard").rglob("*.json"))
    receipt_bytes = {path: path.read_bytes() for path in receipt_paths}

    second = adapter.fetch(fixture_collection(), tmp_path)

    assert second == first
    assert sorted((tmp_path / "receipts" / "om-leaderboard").rglob("*.json")) == receipt_paths
    assert {path: path.read_bytes() for path in receipt_paths} == receipt_bytes


def test_fetch_reports_partial_source_coverage_without_cross_source_assumptions(
    tmp_path, monkeypatch
):
    tarball = make_tarball(
        {
            "JOURNAL_X/TOUCHSTONE/touchstone.solution": b"touchstone-solution",
            "JOURNAL_X/TOUCHSTONE/touchstone.json": b"{}",
        }
    )
    monkeypatch.setattr(
        "opus_corpus.adapters.om_leaderboard.download_github_tarball",
        lambda owner, repo, revision: tarball,
    )

    result = OmLeaderboardAdapter().fetch(fixture_collection(), tmp_path)

    assert result == AcquisitionResult(
        source_id="om-leaderboard",
        candidate_count=1,
        puzzles_covered=1,
    )
