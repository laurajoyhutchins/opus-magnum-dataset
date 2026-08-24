from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from opus_corpus import github_source
from opus_corpus.adapters.base import AcquisitionResult
from opus_corpus.adapters.om_leaderboard import OmLeaderboardAdapter
from opus_corpus.collections import CollectionDefinition
from opus_corpus.github_source import AcquisitionError


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


def _tarball(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class _Unreadable(io.BytesIO):
    def read(self, *args, **kwargs):
        raise AssertionError("irrelevant archive member payload was read")


class _ChunkedResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def read(self, size: int = -1) -> bytes:
        assert size > 0, "GitHub tarball response must be copied in bounded chunks"
        return super().read(size)


def test_tarball_members_strip_root_and_iterate_in_normalized_path_order():
    iterate = getattr(github_source, "iter_tarball_members", None)
    assert callable(iterate), "streaming tarball member iterator is required"
    payload = _tarball(
        [
            ("github-root/z.txt", b"z"),
            ("github-root/a.txt", b"a"),
        ]
    )

    observed = [(path, stream.read()) for path, stream in iterate(io.BytesIO(payload))]

    assert observed == [("a.txt", b"a"), ("z.txt", b"z")]


def test_tarball_members_reject_duplicate_normalized_paths_before_yielding():
    iterate = getattr(github_source, "iter_tarball_members", None)
    assert callable(iterate), "streaming tarball member iterator is required"
    payload = _tarball(
        [
            ("github-root-a/src/data.txt", b"first"),
            ("github-root-b/src/data.txt", b"second"),
        ]
    )
    members = iterate(io.BytesIO(payload))

    with pytest.raises(AcquisitionError, match="duplicate tarball member after root stripping"):
        next(members)


def test_github_tarball_download_is_copied_in_bounded_chunks(monkeypatch):
    iterate = getattr(github_source, "iter_github_tarball_members", None)
    assert callable(iterate), "streaming pinned GitHub acquisition iterator is required"
    payload = _tarball([("github-root/src/data.txt", b"payload")])
    monkeypatch.setattr(
        github_source,
        "urlopen",
        lambda request, timeout: _ChunkedResponse(payload),
    )

    observed = [(path, stream.read()) for path, stream in iterate("owner", "repo", "revision")]

    assert observed == [("src/data.txt", b"payload")]


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

    cache_root = tmp_path / "cache"
    result = OmLeaderboardAdapter().fetch(_collection(tmp_path), cache_root)

    assert result == AcquisitionResult(
        source_id="om-leaderboard",
        candidate_count=1,
        puzzles_covered=1,
    )
    receipts = list((cache_root / "receipts" / "om-leaderboard").rglob("*.json"))
    objects = [path for path in (cache_root / "objects" / "sha256").rglob("*") if path.is_file()]
    assert len(receipts) == 1
    assert [path.read_bytes() for path in objects] == [b"solution"]
