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
    headers: dict[str, str] = {}

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



def test_github_download_rejects_actual_bytes_beyond_ceiling_even_without_length(
    monkeypatch,
) -> None:
    payload = _tarball([("root/puzzle.solution", b"0123456789")])
    monkeypatch.setattr(github_source, "MAX_COMPRESSED_BYTES", len(payload) - 1)
    monkeypatch.setattr(
        github_source,
        "urlopen",
        lambda request, timeout: _ChunkedResponse(payload),
    )
    with pytest.raises(AcquisitionError, match="download size limit exceeded"):
        list(github_source.iter_github_tarball_members("owner", "repo", "rev"))


def test_github_download_rejects_oversized_declared_content_before_streaming(
    monkeypatch,
) -> None:
    class NoRead(_ChunkedResponse):
        headers = {"Content-Length": "999"}
        def read(self, size: int = -1) -> bytes:
            raise AssertionError("oversized response must not be read")

    monkeypatch.setattr(github_source, "MAX_COMPRESSED_BYTES", 100)
    monkeypatch.setattr(github_source, "urlopen", lambda request, timeout: NoRead(b""))
    with pytest.raises(AcquisitionError, match="download size limit exceeded"):
        list(github_source.iter_github_tarball_members("owner", "repo", "rev"))


def test_tar_member_size_limit_rejects_before_payload_is_consumed(monkeypatch) -> None:
    payload = _tarball([("root/big.solution", b"x" * 16)])
    monkeypatch.setattr(github_source, "MAX_MEMBER_BYTES", 15)
    with pytest.raises(AcquisitionError, match="member size limit exceeded"):
        list(github_source.iter_tarball_members(io.BytesIO(payload)))


def test_tarball_member_count_limit_is_enforced_before_yield(monkeypatch) -> None:
    payload = _tarball([
        ("root/a.txt", b"a"),
        ("root/b.txt", b"b"),
        ("root/c.txt", b"c"),
    ])
    monkeypatch.setattr(github_source, "MAX_ARCHIVE_MEMBERS", 2)
    with pytest.raises(AcquisitionError, match="member count limit exceeded"):
        list(github_source.iter_tarball_members(io.BytesIO(payload)))


def test_tarball_total_size_caps_cumulative_decompressed_source_bytes(
    monkeypatch,
) -> None:
    # These member bodies compress effectively but exceed the exact sum cap.
    payload = _tarball([
        ("root/a.dat", b"a" * 8),
        ("root/b.dat", b"b" * 8),
    ])
    monkeypatch.setattr(github_source, "MAX_MEMBER_BYTES", 20)
    monkeypatch.setattr(github_source, "MAX_TOTAL_UNCOMPRESSED_BYTES", 15)
    with pytest.raises(AcquisitionError, match="total size limit exceeded"):
        list(github_source.iter_tarball_members(io.BytesIO(payload)))


def test_limits_allow_exact_ceiling_for_safe_archive(monkeypatch) -> None:
    payload = _tarball([("root/data.txt", b"exact")])
    monkeypatch.setattr(github_source, "MAX_MEMBER_BYTES", 5)
    monkeypatch.setattr(github_source, "MAX_TOTAL_UNCOMPRESSED_BYTES", 5)
    monkeypatch.setattr(github_source, "MAX_ARCHIVE_MEMBERS", 1)
    assert [
        (name, stream.read())
        for name, stream in github_source.iter_tarball_members(io.BytesIO(payload))
    ] == [("data.txt", b"exact")]
