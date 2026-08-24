from __future__ import annotations

import io
import tarfile
from pathlib import Path

from opus_corpus.adapters.base import AcquisitionResult
from opus_corpus.adapters.om_archive import OmArchiveAdapter
from opus_corpus.collections import CollectionDefinition


def fixture_collection() -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture-2026-08-24",
        inventory_sha256="0" * 64,
        puzzle_count=2,
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
            info = tarfile.TarInfo(name=f"om-archive-fixture/{path}")
            info.size = len(payload)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_fetch_stores_only_collection_solution_candidates(tmp_path, monkeypatch):
    tarball = make_tarball(
        {
            "CHAPTER_1/STABILIZED_WATER/a.solution": b"solution-a",
            "CHAPTER_1/STABILIZED_WATER/b.solution": b"solution-b",
            "CHAPTER_1/STABILIZED_WATER/readme.txt": b"ignore",
            "JOURNAL_CVIII_I/LODESTONE/c.solution": b"unsupported-group",
            "CHAPTER_1/OTHER/d.solution": b"other-puzzle",
        }
    )
    monkeypatch.setattr(
        "opus_corpus.adapters.om_archive.download_github_tarball",
        lambda owner, repo, revision: tarball,
    )

    result = OmArchiveAdapter().fetch(fixture_collection(), tmp_path)

    assert result == AcquisitionResult(
        source_id="om-archive",
        candidate_count=2,
        puzzles_covered=1,
    )
    receipts = sorted((tmp_path / "receipts" / "om-archive").rglob("*.json"))
    assert len(receipts) == 2
    objects = sorted((tmp_path / "objects" / "sha256").rglob("*"))
    assert {path.read_bytes() for path in objects if path.is_file()} == {
        b"solution-a",
        b"solution-b",
    }
