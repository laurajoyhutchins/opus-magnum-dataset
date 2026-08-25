from pathlib import Path

import pytest

from opus_corpus.cache import CacheIntegrityError, ContentAddressedCache


def test_read_receipt_rejects_invalid_utf8_as_cache_integrity_error(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    path = cache.receipt_path("source", "rev", "path/a.solution")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")

    with pytest.raises(CacheIntegrityError):
        cache.read_receipt(path)
