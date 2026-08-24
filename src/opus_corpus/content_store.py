from __future__ import annotations

import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import CorpusError
from .hashing import sha256_bytes, sha256_file

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ContentStoreError(CorpusError):
    """Raised when content-addressed object storage is invalid or corrupt."""


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    byte_length: int
    object_key: str


class ContentStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    @staticmethod
    def _validate_digest(sha256: str) -> str:
        if _SHA256_RE.fullmatch(sha256) is None:
            raise ContentStoreError(f"invalid sha256 digest {sha256!r}")
        return sha256

    @staticmethod
    def _object_key(sha256: str) -> str:
        return f"objects/sha256/{sha256[:2]}/{sha256[2:]}"

    def object_path(self, sha256: str) -> Path:
        digest = self._validate_digest(sha256)
        return self.root / self._object_key(digest)

    def require(self, sha256: str, byte_length: int) -> StoredObject:
        digest = self._validate_digest(sha256)
        if byte_length < 0:
            raise ContentStoreError(f"invalid byte length {byte_length}")
        path = self.object_path(digest)
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise ContentStoreError(f"missing content object for sha256 {digest}") from exc
        except OSError as exc:
            raise ContentStoreError(f"cannot stat content object for sha256 {digest}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise ContentStoreError(f"content object for sha256 {digest} is not a regular file")
        try:
            observed_digest = sha256_file(path)
        except OSError as exc:
            raise ContentStoreError(f"cannot read content object for sha256 {digest}") from exc
        if info.st_size != byte_length:
            raise ContentStoreError(
                f"content object byte length mismatch for sha256 {digest}: "
                f"expected {byte_length}, observed {info.st_size}"
            )
        if observed_digest != digest:
            raise ContentStoreError(f"corrupt content object for sha256 {digest}")
        return StoredObject(digest, byte_length, self._object_key(digest))

    def put_bytes(self, payload: bytes) -> StoredObject:
        digest = sha256_bytes(payload)
        byte_length = len(payload)
        target = self.object_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            return self.require(digest, byte_length)

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                prefix=f".{digest}.",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_path, target)
            except FileExistsError:
                return self.require(digest, byte_length)
            return self.require(digest, byte_length)
        except ContentStoreError:
            raise
        except OSError as exc:
            raise ContentStoreError(f"cannot publish content object for sha256 {digest}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
