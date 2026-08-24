from __future__ import annotations

import pytest

from opus_corpus.cache import CacheIntegrityError, ContentAddressedCache


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
