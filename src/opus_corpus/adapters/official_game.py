from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..cache import ContentAddressedCache
from ..collections import CollectionDefinition
from ..directory_publication import publish_directory
from ..errors import CorpusError
from ..hashing import sha256_bytes
from ..path_safety import resolve_disjoint_trees
from .base import AcquisitionResult, SourceAdapter

_MANIFEST_NAME = "official-puzzles.toml"
_TOP_LEVEL_KEYS = {"schema_version", "snapshot_id", "puzzles"}
_PUZZLE_KEYS = {"puzzle_id", "path"}
_SNAPSHOT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_GAME_PUZZLE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_LEADERBOARD_KEY_PATTERN = re.compile(r"[^A-Z0-9]+")


class OfficialGameAcquisitionError(CorpusError):
    """Raised when explicit local official puzzle acquisition is invalid or ambiguous."""


@dataclass(frozen=True)
class OfficialPuzzleMapping:
    puzzle_id: str
    relative_path: PurePosixPath


@dataclass(frozen=True)
class OfficialPuzzleManifest:
    snapshot_id: str
    mappings: tuple[OfficialPuzzleMapping, ...]


def parse_official_manifest(
    manifest_bytes: bytes,
    collection_ids: set[str],
) -> OfficialPuzzleManifest:
    """Parse and validate the authoritative official/local manifest contract."""
    try:
        manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise OfficialGameAcquisitionError("invalid official-game manifest") from exc

    if set(manifest) != _TOP_LEVEL_KEYS:
        raise OfficialGameAcquisitionError(
            f"{_MANIFEST_NAME} must contain only schema_version, snapshot_id, and puzzles"
        )
    if manifest["schema_version"] != 1:
        raise OfficialGameAcquisitionError(f"{_MANIFEST_NAME} schema_version must be 1")
    snapshot_id = manifest["snapshot_id"]
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        raise OfficialGameAcquisitionError(
            f"{_MANIFEST_NAME} snapshot_id must use only letters, digits, '.', '_', or '-'"
        )
    puzzles = manifest["puzzles"]
    if not isinstance(puzzles, list) or not puzzles:
        raise OfficialGameAcquisitionError(
            f"{_MANIFEST_NAME} puzzles must contain at least one explicit mapping"
        )

    seen_puzzle_ids: set[str] = set()
    seen_paths: set[str] = set()
    mappings: list[OfficialPuzzleMapping] = []
    for index, item in enumerate(puzzles, start=1):
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
        mappings.append(OfficialPuzzleMapping(puzzle_id, relative_path))

    return OfficialPuzzleManifest(snapshot_id, tuple(mappings))


def _read_dumped_puzzle_name(payload: bytes, upstream_path: str) -> str:
    """Read only the stable format/version and embedded puzzle-name header."""
    if len(payload) < 5:
        raise OfficialGameAcquisitionError(f"invalid dumped puzzle header: {upstream_path}")
    if int.from_bytes(payload[:4], "little", signed=True) != 3:
        raise OfficialGameAcquisitionError(
            f"unsupported dumped puzzle format in {upstream_path}; expected format 3"
        )

    offset = 4
    byte_length = 0
    shift = 0
    for index in range(5):
        if offset >= len(payload):
            raise OfficialGameAcquisitionError(
                f"truncated dumped puzzle name length: {upstream_path}"
            )
        current = payload[offset]
        offset += 1
        if index == 4 and current > 0x0F:
            raise OfficialGameAcquisitionError(
                f"invalid dumped puzzle name length: {upstream_path}"
            )
        byte_length |= (current & 0x7F) << shift
        if current & 0x80 == 0:
            break
        shift += 7
    else:
        raise OfficialGameAcquisitionError(
            f"invalid dumped puzzle name length: {upstream_path}"
        )

    end = offset + byte_length
    if end > len(payload):
        raise OfficialGameAcquisitionError(f"truncated dumped puzzle name: {upstream_path}")
    try:
        name = payload[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OfficialGameAcquisitionError(
            f"invalid UTF-8 dumped puzzle name: {upstream_path}"
        ) from exc
    if not name:
        raise OfficialGameAcquisitionError(f"empty dumped puzzle name: {upstream_path}")
    return name


def _leaderboard_key_from_puzzle_name(name: str) -> str:
    return _LEADERBOARD_KEY_PATTERN.sub("_", name.upper()).strip("_")


def _render_official_manifest(
    snapshot_id: str,
    mappings: tuple[OfficialPuzzleMapping, ...],
) -> bytes:
    lines = [
        "schema_version = 1",
        f"snapshot_id = {json.dumps(snapshot_id)}",
        "",
    ]
    for mapping in mappings:
        lines.extend(
            (
                "[[puzzles]]",
                f"puzzle_id = {json.dumps(mapping.puzzle_id)}",
                f"path = {json.dumps(mapping.relative_path.as_posix())}",
                "",
            )
        )
    return "\n".join(lines[:-1]).encode("utf-8") + b"\n"


def prepare_official_source_root(
    collection: CollectionDefinition,
    dump_root: Path,
    destination: Path,
    *,
    snapshot_id: str,
) -> OfficialPuzzleManifest:
    """Turn a fresh game-runtime puzzle dump into an official-game source root.

    The runtime serializer already produced the exact artifact bytes. This step reads
    only each artifact's format/name header to reconcile those bytes to the frozen
    collection, then copies them unchanged into the existing official-game manifest
    contract. Unknown extra game puzzles are ignored; missing or ambiguous collection
    coverage fails closed.
    """
    try:
        dump_root, destination = resolve_disjoint_trees(dump_root, destination)
    except ValueError as exc:
        raise OfficialGameAcquisitionError(str(exc)) from exc

    if destination.exists() or destination.is_symlink():
        raise OfficialGameAcquisitionError(
            f"official-game preparation destination already exists: {destination}"
        )
    if not dump_root.is_dir():
        raise OfficialGameAcquisitionError(
            f"official puzzle dump root is not a directory: {dump_root}"
        )

    collection_rows_by_key: dict[str, dict[str, str]] = {}
    collection_ids = {row["puzzle_id"] for row in collection.inventory_rows}
    for row in collection.inventory_rows:
        key = row["leaderboard_key"]
        if key in collection_rows_by_key:
            raise OfficialGameAcquisitionError(
                f"duplicate leaderboard key in collection: {key}"
            )
        game_puzzle_id = row["game_puzzle_id"]
        if not _GAME_PUZZLE_ID_PATTERN.fullmatch(game_puzzle_id):
            raise OfficialGameAcquisitionError(
                f"unsafe game_puzzle_id in collection: {game_puzzle_id!r}"
            )
        collection_rows_by_key[key] = row

    matched: dict[str, tuple[bytes, str]] = {}
    dump_paths = sorted(dump_root.rglob("*.puzzle"), key=lambda path: path.as_posix())
    if not dump_paths:
        raise OfficialGameAcquisitionError(f"official puzzle dump is empty: {dump_root}")

    for dump_path in dump_paths:
        relative = dump_path.relative_to(dump_root).as_posix()
        if dump_path.is_symlink() or not dump_path.is_file():
            raise OfficialGameAcquisitionError(
                f"unsafe dumped puzzle path: {relative}"
            )
        try:
            payload = dump_path.read_bytes()
        except OSError as exc:
            raise OfficialGameAcquisitionError(
                f"could not read dumped puzzle: {relative}"
            ) from exc
        name = _read_dumped_puzzle_name(payload, relative)
        row = collection_rows_by_key.get(_leaderboard_key_from_puzzle_name(name))
        if row is None:
            continue

        puzzle_id = row["puzzle_id"]
        previous = matched.get(puzzle_id)
        if previous is not None:
            previous_payload, previous_path = previous
            if previous_payload != payload:
                raise OfficialGameAcquisitionError(
                    "ambiguous official puzzle dump for "
                    f"{puzzle_id}: {previous_path} and {relative}"
                )
            continue
        matched[puzzle_id] = (payload, relative)

    missing = [
        row["game_puzzle_id"]
        for row in collection.inventory_rows
        if row["puzzle_id"] not in matched
    ]
    if missing:
        raise OfficialGameAcquisitionError(
            "missing official puzzle coverage: " + ", ".join(missing)
        )

    mappings = tuple(
        OfficialPuzzleMapping(
            row["puzzle_id"],
            PurePosixPath("puzzles") / f"{row['game_puzzle_id']}.puzzle",
        )
        for row in collection.inventory_rows
    )
    manifest_bytes = _render_official_manifest(snapshot_id, mappings)
    manifest = parse_official_manifest(manifest_bytes, collection_ids)

    with publish_directory(destination) as candidate:
        puzzle_root = candidate / "puzzles"
        puzzle_root.mkdir()
        for row, mapping in zip(collection.inventory_rows, mappings, strict=True):
            payload, _ = matched[row["puzzle_id"]]
            (candidate / Path(*mapping.relative_path.parts)).write_bytes(payload)
        (candidate / _MANIFEST_NAME).write_bytes(manifest_bytes)

    return manifest


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
        collection_ids = {row["puzzle_id"] for row in collection.inventory_rows}
        manifest, manifest_bytes = self._load_manifest(source_root, collection_ids)
        revision = f"local-{sha256_bytes(manifest.snapshot_id.encode('utf-8'))}"
        prepared: list[tuple[PurePosixPath, bytes]] = []

        for mapping in manifest.mappings:
            puzzle_id = mapping.puzzle_id
            relative_path = mapping.relative_path
            local_path = (source_root / Path(*relative_path.parts)).resolve()
            try:
                local_path.relative_to(source_root)
            except ValueError as exc:
                detail = (
                    f"puzzle mapping for {puzzle_id} must use a relative .puzzle path "
                    "within the source root"
                )
                raise OfficialGameAcquisitionError(detail) from exc
            if not local_path.is_file():
                raise OfficialGameAcquisitionError(
                    f"missing puzzle file for {puzzle_id}: {relative_path.as_posix()}"
                )
            try:
                payload = local_path.read_bytes()
            except OSError as exc:
                raise OfficialGameAcquisitionError(
                    f"could not read puzzle file for {puzzle_id}: {relative_path.as_posix()}"
                ) from exc
            prepared.append((relative_path, payload))

        cache = ContentAddressedCache(cache_root)
        cache.put_bytes(
            self.source_id,
            revision,
            _MANIFEST_NAME,
            manifest_bytes,
            rights_status="local_fetch_only",
        )
        for relative_path, payload in prepared:
            cache.put_bytes(
                self.source_id,
                revision,
                relative_path.as_posix(),
                payload,
                rights_status="local_fetch_only",
            )

        return AcquisitionResult(
            source_id=self.source_id,
            candidate_count=len(prepared),
            puzzles_covered=len(prepared),
        )

    @staticmethod
    def _load_manifest(
        source_root: Path,
        collection_ids: set[str],
    ) -> tuple[OfficialPuzzleManifest, bytes]:
        manifest_path = source_root / _MANIFEST_NAME
        try:
            manifest_bytes = manifest_path.read_bytes()
        except OSError as exc:
            raise OfficialGameAcquisitionError(
                f"invalid official-game manifest: {manifest_path}"
            ) from exc
        return parse_official_manifest(manifest_bytes, collection_ids), manifest_bytes
