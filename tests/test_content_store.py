from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from opus_corpus.content_store import ContentStore, ContentStoreError


def test_put_bytes_preserves_existing_object_layout(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    payload = b"abc"
    digest = hashlib.sha256(payload).hexdigest()

    stored = store.put_bytes(payload)

    assert stored.sha256 == digest
    assert stored.byte_length == len(payload)
    assert stored.object_key == f"objects/sha256/{digest[:2]}/{digest[2:]}"
    assert store.object_path(digest) == tmp_path / stored.object_key
    assert store.object_path(digest).read_bytes() == payload


def test_put_bytes_is_idempotent_for_identical_bytes(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)

    assert store.put_bytes(b"same") == store.put_bytes(b"same")


def test_distinct_bytes_produce_distinct_objects(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)

    first = store.put_bytes(b"first")
    second = store.put_bytes(b"second")

    assert first.sha256 != second.sha256
    assert first.object_key != second.object_key


def test_require_accepts_valid_existing_object(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.put_bytes(b"payload")

    assert store.require(stored.sha256, stored.byte_length) == stored


def test_require_rejects_missing_object(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"missing").hexdigest()

    with pytest.raises(ContentStoreError, match="missing content object"):
        ContentStore(tmp_path).require(digest, 7)


def test_require_rejects_corrupt_object(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    payload = b"expected"
    digest = hashlib.sha256(payload).hexdigest()
    path = store.object_path(digest)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt!")

    with pytest.raises(ContentStoreError, match="corrupt content object"):
        store.require(digest, len(payload))


def test_require_rejects_byte_length_mismatch(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.put_bytes(b"payload")

    with pytest.raises(ContentStoreError, match="byte length mismatch"):
        store.require(stored.sha256, stored.byte_length + 1)


def test_require_rejects_symlink_object(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    real = tmp_path / "real"
    real.write_bytes(payload)
    path = store.object_path(digest)
    path.parent.mkdir(parents=True)
    path.symlink_to(real)

    with pytest.raises(ContentStoreError, match="not a regular file"):
        store.require(digest, len(payload))


@pytest.mark.parametrize("digest", ["", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_invalid_digest_fails_explicitly(tmp_path: Path, digest: str) -> None:
    with pytest.raises(ContentStoreError, match="invalid sha256 digest"):
        ContentStore(tmp_path).object_path(digest)


def test_concurrent_mismatching_winner_is_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ContentStore(tmp_path)
    payload = b"expected"
    digest = hashlib.sha256(payload).hexdigest()
    target = store.object_path(digest)

    def publish_corrupt_winner(src: Path, dst: Path) -> None:
        Path(dst).write_bytes(b"corrupt")
        raise FileExistsError

    monkeypatch.setattr(os, "link", publish_corrupt_winner)

    with pytest.raises(ContentStoreError):
        store.put_bytes(payload)

    assert target.read_bytes() == b"corrupt"


def test_publication_temp_files_are_removed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.put_bytes(b"payload")
    directory = store.object_path(stored.sha256).parent

    assert [path for path in directory.iterdir() if path.name.startswith(f".{stored.sha256}.")] == []
