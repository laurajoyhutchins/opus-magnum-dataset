from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath

from jsonschema import Draft202012Validator

from .content_store import ContentStore, ContentStoreError
from .errors import CorpusError
from .path_safety import require_directory_chain
from .schema_resources import collect_schema_errors, load_schema_resource


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
        self._receipt_validator = Draft202012Validator(
            load_schema_resource("cache-receipt.schema.json").schema
        )

    def object_path(self, sha256: str) -> Path:
        return self.store.object_path(sha256)

    @staticmethod
    def _validate_receipt_component(name: str, value: str) -> str:
        if not isinstance(value, str):
            raise CacheIntegrityError(f"invalid cache receipt {name}: expected string")
        if (
            value in {"", ".", ".."}
            or "/" in value
            or "\\" in value
            or "\0" in value
            or PureWindowsPath(value).drive
        ):
            raise CacheIntegrityError(f"invalid cache receipt {name}: {value!r}")
        return value

    @staticmethod
    def _validate_string(name: str, value: object) -> str:
        if not isinstance(value, str):
            raise CacheIntegrityError(f"invalid cache receipt field {name}: expected string")
        return value

    def receipt_path(self, source_id: str, revision: str, upstream_path: str) -> Path:
        source_id = self._validate_receipt_component("source_id", source_id)
        revision = self._validate_receipt_component("revision", revision)
        upstream_path = self._validate_string("upstream_path", upstream_path)
        identity = f"{source_id}\0{revision}\0{upstream_path}".encode()
        key = hashlib.sha256(identity).hexdigest()
        return self.root / "receipts" / source_id / revision / f"{key}.json"

    def _validate_receipt_parent(self, path: Path, *, create: bool) -> bool:
        try:
            return require_directory_chain(self.root, path.parent, create=create)
        except ValueError as exc:
            raise CacheIntegrityError(f"invalid cache receipt parent: {path.parent}") from exc

    def read_receipt(self, path: Path) -> CacheReceipt:
        """Decode and validate one canonical cache receipt."""

        path = Path(path)
        self._validate_receipt_parent(path, create=False)
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise CacheIntegrityError(f"invalid cache receipt: {path}")
            data = json.loads(path.read_text(encoding="utf-8"))
        except CacheIntegrityError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CacheIntegrityError(f"invalid cache receipt: {path}") from exc

        errors = collect_schema_errors(
            self._receipt_validator,
            data,
            code="cache_receipt_schema_error",
            path=path.as_posix(),
        )
        if errors:
            raise CacheIntegrityError(f"invalid cache receipt: {path}")
        assert isinstance(data, dict)

        receipt = CacheReceipt(
            source_id=data["source_id"],
            revision=data["revision"],
            upstream_path=data["upstream_path"],
            sha256=data["sha256"],
            byte_length=data["byte_length"],
            rights_status=data["rights_status"],
            retrieved_at=data["retrieved_at"],
        )
        expected_path = self.receipt_path(
            receipt.source_id,
            receipt.revision,
            receipt.upstream_path,
        )
        if path.absolute() != expected_path.absolute():
            raise CacheIntegrityError(f"cache receipt identity mismatch: {path}")
        return receipt

    def iter_receipts(self, source_id: str, revision: str) -> Iterator[CacheReceipt]:
        """Yield pinned-source receipts after validating their stored identity."""

        source_id = self._validate_receipt_component("source_id", source_id)
        revision = self._validate_receipt_component("revision", revision)
        receipt_root = self.root / "receipts" / source_id / revision
        try:
            parents_exist = require_directory_chain(
                self.root,
                receipt_root,
                create=False,
            )
        except ValueError as exc:
            raise CacheIntegrityError(f"invalid cache receipt parent: {receipt_root}") from exc
        if not parents_exist:
            return

        for path in sorted(receipt_root.glob("*.json")):
            receipt = self.read_receipt(path)
            if receipt.source_id != source_id or receipt.revision != revision:
                raise CacheIntegrityError(f"cache receipt identity mismatch: {path}")
            yield receipt

    @staticmethod
    def _receipt_facts(receipt: CacheReceipt) -> tuple[str, str, str, str, int, str]:
        return (
            receipt.source_id,
            receipt.revision,
            receipt.upstream_path,
            receipt.sha256,
            receipt.byte_length,
            receipt.rights_status,
        )

    def _require_matching_receipt(
        self,
        path: Path,
        expected: tuple[str, str, str, str, int, str],
    ) -> CacheReceipt:
        existing = self.read_receipt(path)
        if self._receipt_facts(existing) != expected:
            source_id, revision, upstream_path, _, _, _ = expected
            raise CacheIntegrityError(
                f"pinned source path changed: {source_id}@{revision}:{upstream_path}"
            )
        return existing

    def _publish_receipt(
        self,
        path: Path,
        receipt: CacheReceipt,
        expected: tuple[str, str, str, str, int, str],
    ) -> CacheReceipt:
        payload = (
            json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        temp_path: Path | None = None
        try:
            self._validate_receipt_parent(path, create=True)
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_path, path)
            except FileExistsError:
                return self._require_matching_receipt(path, expected)
            return self._require_matching_receipt(path, expected)
        except CacheIntegrityError:
            raise
        except OSError as exc:
            raise CacheIntegrityError(f"cannot publish cache receipt: {path}") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    # Publication outcome is already determined. Preserve either
                    # the committed result or the primary failure; residue is safer
                    # to retain than reporting a false publication outcome.
                    pass

    def put_bytes(
        self,
        source_id: str,
        revision: str,
        upstream_path: str,
        payload: bytes,
        *,
        rights_status: str,
    ) -> CacheReceipt:
        receipt_path = self.receipt_path(source_id, revision, upstream_path)
        rights_status = self._validate_string("rights_status", rights_status)
        try:
            stored = self.store.put_bytes(payload)
        except ContentStoreError as exc:
            raise CacheIntegrityError(str(exc)) from exc

        expected = (
            source_id,
            revision,
            upstream_path,
            stored.sha256,
            stored.byte_length,
            rights_status,
        )
        if receipt_path.exists() or receipt_path.is_symlink():
            return self._require_matching_receipt(receipt_path, expected)

        receipt = CacheReceipt(
            source_id=source_id,
            revision=revision,
            upstream_path=upstream_path,
            sha256=stored.sha256,
            byte_length=stored.byte_length,
            rights_status=rights_status,
            retrieved_at=dt.datetime.now(dt.UTC).isoformat(),
        )
        return self._publish_receipt(receipt_path, receipt, expected)
