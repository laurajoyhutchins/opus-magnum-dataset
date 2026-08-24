from __future__ import annotations

import hashlib
from pathlib import Path

from opus_corpus.content_store import ContentStore


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
