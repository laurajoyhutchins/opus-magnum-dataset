from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from .content_store import ContentStore, ContentStoreError
from .errors import CorpusError


class CacheIntegrityError(CorpusError):
    """Raised when cached facts disagree with a pinned source identity."""


@dataclass(frozen=True)
class CacheReceipt:
    source_id: str
    revision: str
    upstream_path: str
    sha256: str
    byte_length: int
    rights_status: str
    retrieved_at: str


class ContentAddressedCache:
    """Local cache of immutable source bytes plus provenance receipts."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.store = ContentStore(self.root)

    def object_path(self, sha256: str) -> Path:
        return self.store.object_path(sha256)

    def receipt_path(self, source_id: str, revision: str, upstream_path: str) -> Path:
        identity = f"{source_id}\0{revision}\0{upstream_path}".encode()
        key = hashlib.sha256(identity).hexdigest()
        return self.root / "receipts" / source_id / revision / f"{key}.json"

    def iter_receipts(self, source_id: str, revision: str) -> Iterator[CacheReceipt]:
        """Yield pinned-source receipts after validating their stored identity."""

        receipt_root = self.root / "receipts" / source_id / revision
        if not receipt_root.exists():
            return

        for path in sorted(receipt_root.glob("*.json")):
            receipt = self._read_receipt(path)
            expected_path = self.receipt_path(
                receipt.source_id,
                receipt.revision,
                receipt.upstream_path,
            )
            if (
                receipt.source_id != source_id
                or receipt.revision != revision
                or path != expected_path
            ):
                raise CacheIntegrityError(f"cache receipt identity mismatch: {path}")
            yield receipt

    def put_bytes(
        self,
        source_id: str,
        revision: str,
        upstream_path: str,
        payload: bytes,
        *,
        rights_status: str,
    ) -> CacheReceipt:
        try:
            stored = self.store.put_bytes(payload)
        except ContentStoreError as exc:
            raise CacheIntegrityError(str(exc)) from exc

        receipt_path = self.receipt_path(source_id, revision, upstream_path)
        if receipt_path.exists():
            existing = self._read_receipt(receipt_path)
            expected = (
                source_id,
                revision,
                upstream_path,
                stored.sha256,
                stored.byte_length,
                rights_status,
            )
            observed = (
                existing.source_id,
                existing.revision,
                existing.upstream_path,
                existing.sha256,
                existing.byte_length,
                existing.rights_status,
            )
            if observed != expected:
                raise CacheIntegrityError(
                    f"pinned source path changed: {source_id}@{revision}:{upstream_path}"
                )
            return existing

        receipt = CacheReceipt(
            source_id=source_id,
            revision=revision,
            upstream_path=upstream_path,
            sha256=stored.sha256,
            byte_length=stored.byte_length,
            rights_status=rights_status,
            retrieved_at=dt.datetime.now(dt.UTC).isoformat(),
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return receipt

    @staticmethod
    def _read_receipt(path: Path) -> CacheReceipt:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CacheReceipt(**data)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise CacheIntegrityError(f"invalid cache receipt: {path}") from exc
