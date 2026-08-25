from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import opus_corpus.cache as cache_module
import opus_corpus.content_store as store_module
from opus_corpus.cache import CacheIntegrityError, ContentAddressedCache
from opus_corpus.content_store import ContentStore, ContentStoreError
from opus_corpus.directory_publication import publish_directory


def _fail_unlink_for_prefix(monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    original_unlink = Path.unlink

    def unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(prefix):
            raise OSError("simulated cleanup failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)


def test_content_store_preserves_success_when_temp_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    store = ContentStore(tmp_path)
    _fail_unlink_for_prefix(monkeypatch, f".{digest}.")

    stored = store.put_bytes(payload)

    assert stored.sha256 == digest
    assert store.object_path(digest).read_bytes() == payload
    assert any(
        path.name.startswith(f".{digest}.")
        for path in store.object_path(digest).parent.iterdir()
    )


def test_content_store_cleanup_does_not_mask_publish_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    store = ContentStore(tmp_path)
    _fail_unlink_for_prefix(monkeypatch, f".{digest}.")

    def fail_link(_source: object, _target: object) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr(store_module.os, "link", fail_link)

    with pytest.raises(ContentStoreError, match="cannot publish content object") as raised:
        store.put_bytes(payload)

    assert isinstance(raised.value.__cause__, OSError)
    assert str(raised.value.__cause__) == "simulated publish failure"


def test_receipt_publication_preserves_success_when_temp_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt_path = cache.receipt_path("source", "rev", "path.solution")
    _fail_unlink_for_prefix(monkeypatch, f".{receipt_path.name}.")

    receipt = cache.put_bytes(
        "source",
        "rev",
        "path.solution",
        b"payload",
        rights_status="local_fetch_only",
    )

    assert cache.read_receipt(receipt_path) == receipt
    assert any(
        path.name.startswith(f".{receipt_path.name}.")
        for path in receipt_path.parent.iterdir()
    )


def test_receipt_cleanup_does_not_mask_publish_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt_path = cache.receipt_path("source", "rev", "path.solution")
    _fail_unlink_for_prefix(monkeypatch, f".{receipt_path.name}.")

    def fail_link(_source: object, _target: object) -> None:
        raise OSError("simulated receipt publish failure")

    monkeypatch.setattr(
        cache_module,
        "os",
        SimpleNamespace(link=fail_link, fsync=os.fsync),
        raising=False,
    )

    with pytest.raises(CacheIntegrityError, match="cannot publish cache receipt") as raised:
        cache.put_bytes(
            "source",
            "rev",
            "path.solution",
            b"payload",
            rights_status="local_fetch_only",
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert str(raised.value.__cause__) == "simulated receipt publish failure"


def test_directory_candidate_cleanup_does_not_mask_domain_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "published"

    import opus_corpus.directory_publication as publication_module

    original_remove = publication_module._remove_path

    def fail_candidate_cleanup(path: Path) -> None:
        if ".candidate-" in path.name:
            raise OSError("simulated candidate cleanup failure")
        original_remove(path)

    monkeypatch.setattr(publication_module, "_remove_path", fail_candidate_cleanup)

    with pytest.raises(RuntimeError, match="primary domain failure"):
        with publish_directory(destination):
            raise RuntimeError("primary domain failure")
