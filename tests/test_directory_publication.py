from pathlib import Path

import pytest

import opus_corpus.directory_publication as directory_publication
from opus_corpus.directory_publication import publish_directory


def test_backup_cleanup_failure_after_promotion_does_not_report_publication_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "release"
    destination.mkdir()
    (destination / "state.txt").write_text("old", encoding="utf-8")
    real_remove_path = directory_publication._remove_path

    def fail_backup_cleanup(path: Path) -> None:
        if ".previous-" in path.name:
            raise OSError("injected backup cleanup failure")
        real_remove_path(path)

    monkeypatch.setattr(directory_publication, "_remove_path", fail_backup_cleanup)

    with publish_directory(destination) as candidate:
        (candidate / "state.txt").write_text("new", encoding="utf-8")

    assert (destination / "state.txt").read_text(encoding="utf-8") == "new"
    backups = sorted(tmp_path.glob(".release.previous-*"))
    assert len(backups) == 1
    assert (backups[0] / "state.txt").read_text(encoding="utf-8") == "old"