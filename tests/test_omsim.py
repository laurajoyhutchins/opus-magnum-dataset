from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from opus_corpus.adapters.base import AcquisitionResult
from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.collections import CollectionDefinition
from opus_corpus.github_source import AcquisitionError, iter_tarball_members


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
                "puzzle_id": "om.puzzle.0002",
                "display_name": "Refined Gold",
                "kind": "campaign",
                "group": "chapter-1",
                "game_puzzle_id": "P010",
                "leaderboard_key": "REFINED_GOLD",
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
            info = tarfile.TarInfo(name=f"omsim-fixture/{path}")
            info.size = len(payload)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def mock_tarball(monkeypatch, tarball: bytes) -> None:
    monkeypatch.setattr(
        "opus_corpus.adapters.omsim.iter_github_tarball_members",
        lambda owner, repo, revision: iter_tarball_members(io.BytesIO(tarball)),
    )


def test_fetch_stores_only_collection_campaign_puzzle_fixtures(tmp_path, monkeypatch):
    tarball = make_tarball(
        {
            "test/puzzle/campaign/ch1-and-prologue/P007.puzzle": b"p007-puzzle",
            "test/puzzle/campaign/ch1-and-prologue/P010.puzzle": b"p010-puzzle",
            "test/puzzle/campaign/ch1-and-prologue/P999.puzzle": b"other-campaign",
            "test/puzzle/journal/issue-1/P256.puzzle": b"historical-journal",
            "test/puzzle/campaign/ch1-and-prologue/readme.txt": b"ignore",
        }
    )
    mock_tarball(monkeypatch, tarball)

    result = OmsimAdapter().fetch(fixture_collection(), tmp_path)

    assert result == AcquisitionResult(
        source_id="omsim",
        candidate_count=2,
        puzzles_covered=2,
    )
    receipts = sorted((tmp_path / "receipts" / "omsim").rglob("*.json"))
    assert len(receipts) == 2
    receipt_data = [json.loads(path.read_text(encoding="utf-8")) for path in receipts]
    assert {receipt["rights_status"] for receipt in receipt_data} == {"local_fetch_only"}
    assert {receipt["revision"] for receipt in receipt_data} == {OmsimAdapter.pinned_revision}
    assert {receipt["upstream_path"] for receipt in receipt_data} == {
        "test/puzzle/campaign/ch1-and-prologue/P007.puzzle",
        "test/puzzle/campaign/ch1-and-prologue/P010.puzzle",
    }
    objects = sorted((tmp_path / "objects" / "sha256").rglob("*"))
    assert {path.read_bytes() for path in objects if path.is_file()} == {
        b"p007-puzzle",
        b"p010-puzzle",
    }


def test_fetch_rejects_duplicate_campaign_fixture_for_same_game_id(tmp_path, monkeypatch):
    tarball = make_tarball(
        {
            "test/puzzle/campaign/a/P007.puzzle": b"first",
            "test/puzzle/campaign/b/P007.puzzle": b"second",
        }
    )
    mock_tarball(monkeypatch, tarball)

    with pytest.raises(AcquisitionError, match="multiple campaign fixtures.*P007"):
        OmsimAdapter().fetch(fixture_collection(), tmp_path)

    assert not (tmp_path / "receipts").exists()
    assert not (tmp_path / "objects").exists()


def test_fetch_is_idempotent_for_same_pinned_source(tmp_path, monkeypatch):
    tarball = make_tarball(
        {"test/puzzle/campaign/ch1-and-prologue/P007.puzzle": b"p007-puzzle"}
    )
    calls: list[tuple[str, str, str]] = []

    def fake_members(owner: str, repo: str, revision: str):
        calls.append((owner, repo, revision))
        return iter_tarball_members(io.BytesIO(tarball))

    monkeypatch.setattr(
        "opus_corpus.adapters.omsim.iter_github_tarball_members",
        fake_members,
    )
    adapter = OmsimAdapter()

    first = adapter.fetch(fixture_collection(), tmp_path)
    receipts = sorted((tmp_path / "receipts" / "omsim").rglob("*.json"))
    before = {path: path.read_bytes() for path in receipts}
    second = adapter.fetch(fixture_collection(), tmp_path)
    after_receipts = sorted((tmp_path / "receipts" / "omsim").rglob("*.json"))
    after = {path: path.read_bytes() for path in after_receipts}
    object_files = [
        path
        for path in (tmp_path / "objects" / "sha256").rglob("*")
        if path.is_file()
    ]

    assert first == second == AcquisitionResult(
        source_id="omsim",
        candidate_count=1,
        puzzles_covered=1,
    )
    assert calls == [
        ("ianh", "omsim", OmsimAdapter.pinned_revision),
        ("ianh", "omsim", OmsimAdapter.pinned_revision),
    ]
    assert len(after_receipts) == 1
    assert len(object_files) == 1
    assert before == after
