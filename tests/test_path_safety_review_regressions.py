from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.path_safety import resolve_confined_path


@pytest.mark.parametrize("relative_path", [None, 123, {"path": "data/file.parquet"}])
def test_resolve_confined_path_rejects_non_string_manifest_paths_as_value_error(
    tmp_path: Path, relative_path: object
):
    with pytest.raises(ValueError, match="manifest path"):
        resolve_confined_path(tmp_path / "root", relative_path)  # type: ignore[arg-type]


def test_resolve_confined_path_rejects_windows_drive_path_with_forward_slashes(
    tmp_path: Path,
):
    with pytest.raises(ValueError, match="manifest path"):
        resolve_confined_path(tmp_path / "root", "C:/escape.parquet")
