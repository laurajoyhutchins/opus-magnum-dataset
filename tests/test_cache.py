from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import opus_corpus.cache as cache_module
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


def test_receipt_publication_failure_leaves_no_canonical_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt_path = cache.receipt_path("source", "rev", "path/a.solution")

    def fail_link(_source: object, _target: object) -> None:
        raise OSError("simulated interrupted publication")

    monkeypatch.setattr(
        cache_module,
        "os",
        SimpleNamespace(link=fail_link, fsync=os.fsync),
        raising=False,
    )

    with pytest.raises(CacheIntegrityError):
        cache.put_bytes(
            "source",
            "rev",
            "path/a.solution",
            b"abc",
            rights_status="local_fetch_only",
        )

    assert not receipt_path.exists()
    assert list(receipt_path.parent.glob(f".{receipt_path.name}.*")) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", 7),
        ("revision", ["rev"]),
        ("upstream_path", None),
        ("sha256", 11),
        ("byte_length", "3"),
        ("byte_length", True),
        ("rights_status", False),
        ("retrieved_at", 123),
    ],
)
def test_read_receipt_rejects_incorrect_field_types(
    tmp_path: Path, field: str, value: object
) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt = cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )
    path = cache.receipt_path("source", "rev", "path/a.solution")
    data = {
        "source_id": receipt.source_id,
        "revision": receipt.revision,
        "upstream_path": receipt.upstream_path,
        "sha256": receipt.sha256,
        "byte_length": receipt.byte_length,
        "rights_status": receipt.rights_status,
        "retrieved_at": receipt.retrieved_at,
    }
    data[field] = value
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")

    with pytest.raises(CacheIntegrityError):
        cache.read_receipt(path)


def test_read_receipt_rejects_partial_json(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    path = cache.receipt_path("source", "rev", "path/a.solution")
    path.parent.mkdir(parents=True)
    path.write_text('{"source_id":', encoding="utf-8")

    with pytest.raises(CacheIntegrityError):
        cache.read_receipt(path)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_read_receipt_rejects_non_exact_shape(tmp_path: Path, mutation: str) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt = cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )
    path = cache.receipt_path("source", "rev", "path/a.solution")
    data = {
        "source_id": receipt.source_id,
        "revision": receipt.revision,
        "upstream_path": receipt.upstream_path,
        "sha256": receipt.sha256,
        "byte_length": receipt.byte_length,
        "rights_status": receipt.rights_status,
        "retrieved_at": receipt.retrieved_at,
    }
    if mutation == "missing":
        del data["rights_status"]
    else:
        data["unexpected"] = "value"
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")

    with pytest.raises(CacheIntegrityError):
        cache.read_receipt(path)


@pytest.mark.parametrize("unsafe", ["", ".", "..", "../escape", "a/b", r"a\\b", "a\0b", "C:"])
def test_receipt_path_rejects_unsafe_source_id(tmp_path: Path, unsafe: str) -> None:
    cache = ContentAddressedCache(tmp_path)
    with pytest.raises(CacheIntegrityError):
        cache.receipt_path(unsafe, "rev", "path/a.solution")


@pytest.mark.parametrize("unsafe", ["", ".", "..", "../escape", "a/b", r"a\\b", "a\0b", "C:"])
def test_receipt_path_rejects_unsafe_revision(tmp_path: Path, unsafe: str) -> None:
    cache = ContentAddressedCache(tmp_path)
    with pytest.raises(CacheIntegrityError):
        cache.receipt_path("source", unsafe, "path/a.solution")


def test_read_receipt_rejects_path_identity_mismatch(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )
    original = cache.receipt_path("source", "rev", "path/a.solution")
    forged = original.with_name("0" * 64 + ".json")
    forged.write_bytes(original.read_bytes())

    with pytest.raises(CacheIntegrityError):
        cache.read_receipt(forged)

    with pytest.raises(CacheIntegrityError):
        list(cache.iter_receipts("source", "rev"))


def test_conflicting_existing_receipt_is_not_replaced(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    cache.put_bytes(
        "source",
        "rev",
        "path/a.solution",
        b"abc",
        rights_status="local_fetch_only",
    )
    path = cache.receipt_path("source", "rev", "path/a.solution")
    before = path.read_bytes()

    with pytest.raises(CacheIntegrityError):
        cache.put_bytes(
            "source",
            "rev",
            "path/a.solution",
            b"xyz",
            rights_status="local_fetch_only",
        )

    assert path.read_bytes() == before
