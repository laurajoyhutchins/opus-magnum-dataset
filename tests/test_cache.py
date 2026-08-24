from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from opus_corpus.cache import CacheIntegrityError, CacheReceipt, ContentAddressedCache
from opus_corpus.content_store import ContentStore


def test_put_bytes_is_content_addressed_and_idempotent(tmp_path):
    cache = ContentAddressedCache(tmp_path)

    first = cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )
    second = cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )

    assert first == second
    assert cache.object_path(first.sha256).read_bytes() == b"abc"
    assert cache.receipt_path("source", "rev", "path/a.solution").is_file()


def test_put_bytes_rejects_changed_payload_for_pinned_path(tmp_path):
    cache = ContentAddressedCache(tmp_path)
    cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )

    with pytest.raises(CacheIntegrityError):
        cache.put_bytes(
            "source",
            "rev",
            "path/a.solution",
            b"xyz",
            rights_status="local_fetch_only",
        )


def test_receipt_key_distinguishes_upstream_paths(tmp_path):
    cache = ContentAddressedCache(tmp_path)
    left = cache.put_bytes(
        "source",
        "rev",
        "left/a.solution",
        b"same",
        rights_status="local_fetch_only",
    )
    right = cache.put_bytes(
        "source",
        "rev",
        "right/a.solution",
        b"same",
        rights_status="local_fetch_only",
    )

    assert left.sha256 == right.sha256
    assert cache.receipt_path("source", "rev", "left/a.solution") != cache.receipt_path(
        "source", "rev", "right/a.solution"
    )


def test_cache_exposes_shared_content_store(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)

    assert isinstance(cache.store, ContentStore)
    assert cache.store.root == tmp_path


def test_object_path_compatibility_preserves_existing_layout(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt = cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )

    assert cache.object_path(receipt.sha256) == (
        tmp_path / "objects" / "sha256" / receipt.sha256[:2] / receipt.sha256[2:]
    )


def test_preexisting_cache_directory_requires_no_migration(tmp_path: Path) -> None:
    payload = b"legacy-cache-payload"
    digest = hashlib.sha256(payload).hexdigest()
    object_path = tmp_path / "objects" / "sha256" / digest[:2] / digest[2:]
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(payload)
    cache = ContentAddressedCache(tmp_path)
    receipt_path = cache.receipt_path("source", "rev", "path/a.solution")
    receipt_path.parent.mkdir(parents=True)
    old_receipt = {
        "source_id": "source",
        "revision": "rev",
        "upstream_path": "path/a.solution",
        "sha256": digest,
        "byte_length": len(payload),
        "rights_status": "local_fetch_only",
        "retrieved_at": "2026-08-24T12:00:00+00:00",
    }
    receipt_path.write_text(
        json.dumps(old_receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    before = receipt_path.read_bytes()

    receipt = cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        payload,
        rights_status="local_fetch_only",
    )

    assert receipt == CacheReceipt(**old_receipt)
    assert receipt_path.read_bytes() == before
    assert object_path.read_bytes() == payload
