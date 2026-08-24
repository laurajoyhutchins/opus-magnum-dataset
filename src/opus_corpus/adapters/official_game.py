from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..cache import ContentAddressedCache
from ..collections import CollectionDefinition
from ..errors import CorpusError
from .base import AcquisitionResult, SourceAdapter

_MANIFEST_NAME = "official-puzzles.toml"
_TOP_LEVEL_KEYS = {"schema_version", "snapshot_id", "puzzles"}
_PUZZLE_KEYS = {"puzzle_id", "path"}


class OfficialGameAcquisitionError(CorpusError):
    """Raised when explicit local official puzzle acquisition is invalid or ambiguous."""


@dataclass(frozen=True)
class OfficialGameAdapter(SourceAdapter):
    source_root: Path | None = None

    source_id = "official-game"
    pinned_revision = None

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> AcquisitionResult:
        if self.source_root is None:
            raise OfficialGameAcquisitionError(
                "official-game acquisition requires an explicit local source root"
            )

        source_root = Path(self.source_root).resolve()
        manifest = self._load_manifest(source_root)
        snapshot_id = manifest["snapshot_id"]
        revision = f"local:{snapshot_id}"
        collection_ids = {row["puzzle_id"] for row in collection.inventory_rows}
        cache = ContentAddressedCache(cache_root)
        seen_puzzle_ids: set[str] = set()
        seen_paths: set[str] = set()

        for index, item in enumerate(manifest["puzzles"], start=1):
            puzzle_id, relative_path = self._validate_mapping(
                item,
                index=index,
                collection_ids=collection_ids,
                seen_puzzle_ids=seen_puzzle_ids,
                seen_paths=seen_paths,
            )
            local_path = (source_root / Path(*relative_path.parts)).resolve()
            try:
                local_path.relative_to(source_root)
            except ValueError as exc:
                detail = (
                    f"puzzle mapping {index} must use a relative .puzzle path "
                    "within the source root"
                )
                raise OfficialGameAcquisitionError(detail) from exc
            if not local_path.is_file():
                raise OfficialGameAcquisitionError(
                    f"missing puzzle file for {puzzle_id}: {relative_path.as_posix()}"
                )

            cache.put_bytes(
                self.source_id,
                revision,
                relative_path.as_posix(),
                local_path.read_bytes(),
                rights_status="local_fetch_only",
            )

        return AcquisitionResult(
            source_id=self.source_id,
            candidate_count=len(seen_puzzle_ids),
            puzzles_covered=len(seen_puzzle_ids),
        )

    @staticmethod
    def _load_manifest(source_root: Path) -> dict:
        manifest_path = source_root / _MANIFEST_NAME
        try:
            with manifest_path.open("rb") as handle:
                manifest = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise OfficialGameAcquisitionError(
                f"invalid official-game manifest: {manifest_path}"
            ) from exc

        if set(manifest) != _TOP_LEVEL_KEYS:
            raise OfficialGameAcquisitionError(
                f"{_MANIFEST_NAME} must contain only schema_version, snapshot_id, and puzzles"
            )
        if manifest["schema_version"] != 1:
            raise OfficialGameAcquisitionError(f"{_MANIFEST_NAME} schema_version must be 1")
        snapshot_id = manifest["snapshot_id"]
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise OfficialGameAcquisitionError(f"{_MANIFEST_NAME} snapshot_id must be non-empty")
        puzzles = manifest["puzzles"]
        if not isinstance(puzzles, list) or not puzzles:
            raise OfficialGameAcquisitionError(
                f"{_MANIFEST_NAME} puzzles must contain at least one explicit mapping"
            )
        return manifest

    @staticmethod
    def _validate_mapping(
        item: object,
        *,
        index: int,
        collection_ids: set[str],
        seen_puzzle_ids: set[str],
        seen_paths: set[str],
    ) -> tuple[str, PurePosixPath]:
        if not isinstance(item, dict) or set(item) != _PUZZLE_KEYS:
            raise OfficialGameAcquisitionError(
                f"puzzle mapping {index} must contain only puzzle_id and path"
            )
        puzzle_id = item["puzzle_id"]
        raw_path = item["path"]
        if not isinstance(puzzle_id, str) or not puzzle_id:
            raise OfficialGameAcquisitionError(f"puzzle mapping {index} has invalid puzzle_id")
        if puzzle_id not in collection_ids:
            raise OfficialGameAcquisitionError(f"puzzle_id {puzzle_id!r} is not in collection")
        if puzzle_id in seen_puzzle_ids:
            raise OfficialGameAcquisitionError(f"duplicate puzzle_id mapping: {puzzle_id}")
        if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
            raise OfficialGameAcquisitionError(
                f"puzzle mapping {index} must use a relative .puzzle path"
            )

        relative_path = PurePosixPath(raw_path)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.suffix != ".puzzle"
        ):
            raise OfficialGameAcquisitionError(
                f"puzzle mapping {index} must use a relative .puzzle path"
            )
        upstream_path = relative_path.as_posix()
        if upstream_path in seen_paths:
            raise OfficialGameAcquisitionError(f"duplicate path mapping: {upstream_path}")

        seen_puzzle_ids.add(puzzle_id)
        seen_paths.add(upstream_path)
        return puzzle_id, relative_path
