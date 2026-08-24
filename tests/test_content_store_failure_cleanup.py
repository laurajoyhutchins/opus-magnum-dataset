from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from opus_corpus.content_store import ContentStore, ContentStoreError


def test_publication_temp_files_are_removed_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ContentStore(tmp_path)
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    directory = store.object_path(digest).parent

    def fail_publish(src: Path, dst: Path) -> None:
        raise OSError("publish failed")

    monkeypatch.setattr(os, "link", fail_publish)

    with pytest.raises(ContentStoreError, match="cannot publish content object"):
        store.put_bytes(payload)

    assert directory.is_dir()
    temp_files = [path for path in directory.iterdir() if path.name.startswith(f".{digest}.")]
    assert temp_files == []
