from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from opus_corpus.cache import CacheIntegrityError, ContentAddressedCache
from opus_corpus.content_store import ContentStore, ContentStoreError


def _write_receipt(path: Path, *, sha256: str, byte_length: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source_id": "source",
                "revision": "rev",
                "upstream_path": "path.solution",
                "sha256": sha256,
                "byte_length": byte_length,
                "rights_status": "local_fetch_only",
                "retrieved_at": "2026-08-24T12:00:00+00:00",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def test_read_receipt_rejects_symlinked_revision_parent(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path / "cache")
    receipt_path = cache.receipt_path("source", "rev", "path.solution")
    external = tmp_path / "external"
    external.mkdir()
    revision_parent = receipt_path.parent
    revision_parent.parent.mkdir(parents=True)
    revision_parent.symlink_to(external, target_is_directory=True)
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    _write_receipt(external / receipt_path.name, sha256=digest, byte_length=len(payload))

    with pytest.raises(CacheIntegrityError, match="invalid cache receipt parent"):
        cache.read_receipt(receipt_path)


def test_iter_receipts_rejects_symlinked_revision_parent(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path / "cache")
    receipt_root = cache.receipt_path("source", "rev", "path.solution").parent
    external = tmp_path / "external"
    external.mkdir()
    receipt_root.parent.mkdir(parents=True)
    receipt_root.symlink_to(external, target_is_directory=True)

    with pytest.raises(CacheIntegrityError, match="invalid cache receipt parent"):
        list(cache.iter_receipts("source", "rev"))


def test_receipt_publication_rejects_symlinked_revision_parent(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path / "cache")
    receipt_path = cache.receipt_path("source", "rev", "path.solution")
    external = tmp_path / "external"
    external.mkdir()
    receipt_path.parent.parent.mkdir(parents=True)
    receipt_path.parent.symlink_to(external, target_is_directory=True)

    with pytest.raises(CacheIntegrityError, match="invalid cache receipt parent"):
        cache.put_bytes(
            "source",
            "rev",
            "path.solution",
            b"payload",
            rights_status="local_fetch_only",
        )

    assert list(external.iterdir()) == []


def test_iter_receipts_rejects_regular_file_parent_collision(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path / "cache")
    cache.root.mkdir()
    (cache.root / "receipts").write_text("not a directory", encoding="utf-8")

    with pytest.raises(CacheIntegrityError, match="invalid cache receipt parent"):
        list(cache.iter_receipts("source", "rev"))


def test_content_store_require_rejects_symlinked_object_prefix(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    store = ContentStore(root)
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    target = store.object_path(digest)
    external = tmp_path / "external"
    external.mkdir()
    target.parent.parent.mkdir(parents=True)
    target.parent.symlink_to(external, target_is_directory=True)
    (external / target.name).write_bytes(payload)

    with pytest.raises(ContentStoreError, match="invalid content object parent"):
        store.require(digest, len(payload))


def test_content_store_put_rejects_symlinked_object_prefix(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    store = ContentStore(root)
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    target = store.object_path(digest)
    external = tmp_path / "external"
    external.mkdir()
    target.parent.parent.mkdir(parents=True)
    target.parent.symlink_to(external, target_is_directory=True)

    with pytest.raises(ContentStoreError, match="invalid content object parent"):
        store.put_bytes(payload)

    assert list(external.iterdir()) == []


def test_content_store_put_rejects_regular_file_parent_collision(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    root.mkdir()
    (root / "objects").write_text("not a directory", encoding="utf-8")
    store = ContentStore(root)

    with pytest.raises(ContentStoreError, match="invalid content object parent"):
        store.put_bytes(b"payload")
