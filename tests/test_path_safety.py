from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.path_safety import resolve_confined_path


@pytest.mark.parametrize(
    "relative_path",
    [
        "/tmp/escape.parquet",
        "C:\\escape.parquet",
        "../escape.parquet",
        "data/../escape.parquet",
        "data/./split.parquet",
    ],
)
def test_resolve_confined_path_rejects_unsafe_lexical_paths(
    tmp_path: Path, relative_path: str
):
    with pytest.raises(ValueError):
        resolve_confined_path(tmp_path / "root", relative_path)


def test_resolve_confined_path_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "data").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escape"):
        resolve_confined_path(root, "data/escape.parquet")


def test_resolve_confined_path_returns_canonical_contained_path(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    resolved = resolve_confined_path(root, "data/puzzles/split.parquet")

    assert resolved == root / "data/puzzles/split.parquet"
