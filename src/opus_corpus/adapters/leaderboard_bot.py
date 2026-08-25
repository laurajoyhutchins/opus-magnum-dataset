from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .. import github_source
from ..cache import ContentAddressedCache
from ..collections import CollectionDefinition
from ..errors import CorpusError
from .base import AcquisitionResult, SourceAdapter

_MODEL_ROOT = "src/main/kotlin/com/faendir/zachtronics/bot/om/model"
_PUZZLE_MODEL_PATH = f"{_MODEL_ROOT}/OmPuzzle.kt"
_GROUP_MODEL_PATH = f"{_MODEL_ROOT}/OmGroup.kt"
_COLLECTION_MODEL_PATH = f"{_MODEL_ROOT}/OmCollection.kt"
_TYPE_MODEL_PATH = f"{_MODEL_ROOT}/OmType.kt"
_REQUIRED_SOURCE_PATHS = (
    _PUZZLE_MODEL_PATH,
    _GROUP_MODEL_PATH,
    _COLLECTION_MODEL_PATH,
    _TYPE_MODEL_PATH,
)
_QUOTED_STRING = r'"(?:\\.|[^"\\])*"'
_PUZZLE_ENTRY_RE = re.compile(
    rf"^(?P<key>[A-Z][A-Z0-9_]*)\("
    rf"(?P<group>[A-Z][A-Z0-9_]*)\s*,\s*"
    rf"(?P<type>[A-Z][A-Z0-9_]*)\s*,\s*"
    rf"(?P<display>{_QUOTED_STRING})\s*,\s*"
    rf"(?P<id>{_QUOTED_STRING})"
    rf"(?P<alts>(?:\s*,\s*{_QUOTED_STRING})*)"
    rf"\)\s*,?$"
)
_GROUP_ENTRY_RE = re.compile(
    rf"^(?P<key>[A-Z][A-Z0-9_]*)\("
    rf"(?P<collection>[A-Z][A-Z0-9_]*)\s*,\s*"
    rf"(?P<display>{_QUOTED_STRING})"
    rf"\)\s*,?$"
)
_NAMED_ENTRY_RE = re.compile(
    rf"^(?P<key>[A-Z][A-Z0-9_]*)\((?P<display>{_QUOTED_STRING})\)\s*,?$"
)


class LeaderboardBotDataError(CorpusError):
    """Raised when pinned leaderboard-bot model evidence cannot be reconciled."""


@dataclass(frozen=True)
class LeaderboardBotPuzzleEvidence:
    puzzle_id: str
    leaderboard_key: str
    game_puzzle_id: str
    display_name: str
    kind: str
    group: str
    puzzle_type: str


@dataclass(frozen=True)
class _UpstreamPuzzle:
    leaderboard_key: str
    game_puzzle_id: str
    display_name: str
    group_key: str
    type_key: str


class LeaderboardBotAdapter(SourceAdapter):
    source_id = "leaderboard-bot"
    pinned_revision = "ca40dee95da584270eb3be1c4b74e2be63afa7e6"

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> AcquisitionResult:
        files: dict[str, bytes] = {}
        for upstream_path, member in github_source.iter_github_tarball_members(
            "F43nd1r",
            "zachtronics-leaderboard-bot",
            self.pinned_revision,
        ):
            if upstream_path not in _REQUIRED_SOURCE_PATHS:
                continue
            if upstream_path in files:
                raise LeaderboardBotDataError(
                    f"duplicate leaderboard-bot model source {upstream_path!r}"
                )
            files[upstream_path] = member.read()

        missing = [path for path in _REQUIRED_SOURCE_PATHS if path not in files]
        if missing:
            raise LeaderboardBotDataError(
                "pinned leaderboard-bot source is missing " + ", ".join(missing)
            )

        cache = ContentAddressedCache(cache_root)
        for upstream_path in _REQUIRED_SOURCE_PATHS:
            cache.put_bytes(
                self.source_id,
                self.pinned_revision,
                upstream_path,
                files[upstream_path],
                rights_status="local_fetch_only",
            )

        evidence = self.parse_collection_evidence(
            collection,
            puzzle_source=files[_PUZZLE_MODEL_PATH],
            group_source=files[_GROUP_MODEL_PATH],
            collection_source=files[_COLLECTION_MODEL_PATH],
            type_source=files[_TYPE_MODEL_PATH],
        )
        return AcquisitionResult(
            source_id=self.source_id,
            candidate_count=len(_REQUIRED_SOURCE_PATHS),
            puzzles_covered=len(evidence),
        )

    def parse_collection_evidence(
        self,
        collection: CollectionDefinition,
        *,
        puzzle_source: bytes,
        group_source: bytes,
        collection_source: bytes,
        type_source: bytes,
    ) -> tuple[LeaderboardBotPuzzleEvidence, ...]:
        collections = self._parse_named_enum(
            collection_source,
            _COLLECTION_MODEL_PATH,
            "OmCollection",
        )
        groups = self._parse_groups(group_source, collections)
        types = self._parse_named_enum(type_source, _TYPE_MODEL_PATH, "OmType")
        catalog = self._parse_puzzles(puzzle_source, groups, types)

        evidence: list[LeaderboardBotPuzzleEvidence] = []
        errors: list[str] = []
        for row in collection.inventory_rows:
            game_puzzle_id = row["game_puzzle_id"]
            upstream = catalog.get(game_puzzle_id)
            if upstream is None:
                errors.append(f"{game_puzzle_id}: missing from leaderboard-bot puzzle model")
                continue

            source_collection = groups[upstream.group_key]
            source_group = self._canonical_group(upstream.group_key, source_collection)
            source_kind = self._canonical_kind(upstream.group_key, source_collection)
            source_type = types[upstream.type_key].replace(" ", "_")
            comparisons = (
                ("leaderboard_key", row["leaderboard_key"], upstream.leaderboard_key),
                ("display_name", row["display_name"], upstream.display_name),
                ("kind", row["kind"], source_kind),
                ("group", row["group"], source_group),
                ("puzzle_type", row["puzzle_type"], source_type),
            )
            mismatches = [
                f"{field} expected {expected!r} observed {observed!r}"
                for field, expected, observed in comparisons
                if expected != observed
            ]
            if mismatches:
                errors.append(f"{game_puzzle_id}: " + "; ".join(mismatches))
                continue

            evidence.append(
                LeaderboardBotPuzzleEvidence(
                    puzzle_id=row["puzzle_id"],
                    leaderboard_key=upstream.leaderboard_key,
                    game_puzzle_id=game_puzzle_id,
                    display_name=upstream.display_name,
                    kind=source_kind,
                    group=source_group,
                    puzzle_type=source_type,
                )
            )

        if errors:
            raise LeaderboardBotDataError("; ".join(errors))
        return tuple(evidence)

    @staticmethod
    def _decode_source(payload: bytes, path: str) -> str:
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LeaderboardBotDataError(
                f"leaderboard-bot source {path!r} is not UTF-8"
            ) from exc

    @classmethod
    def _enum_constant_lines(
        cls,
        payload: bytes,
        path: str,
        class_name: str,
    ) -> tuple[str, ...]:
        text = cls._decode_source(payload, path)
        marker = f"enum class {class_name}"
        marker_offset = text.find(marker)
        if marker_offset < 0:
            raise LeaderboardBotDataError(
                f"leaderboard-bot source {path!r} is missing {marker}"
            )
        opening = text.find("{", marker_offset + len(marker))
        if opening < 0:
            raise LeaderboardBotDataError(
                f"leaderboard-bot source {path!r} has malformed {class_name}"
            )

        lines: list[str] = []
        for raw_line in text[opening + 1 :].splitlines():
            line = raw_line.strip()
            if line == ";" or line.startswith(";"):
                break
            if re.match(r"^[A-Z][A-Z0-9_]*\(", line):
                lines.append(line)
        if not lines:
            raise LeaderboardBotDataError(
                f"leaderboard-bot source {path!r} contains no {class_name} entries"
            )
        return tuple(lines)

    @classmethod
    def _parse_named_enum(
        cls,
        payload: bytes,
        path: str,
        class_name: str,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in cls._enum_constant_lines(payload, path, class_name):
            match = _NAMED_ENTRY_RE.fullmatch(line)
            if match is None:
                raise LeaderboardBotDataError(
                    f"unparsed {class_name} data in leaderboard-bot source"
                )
            key = match.group("key")
            if key in result:
                raise LeaderboardBotDataError(
                    f"duplicate leaderboard-bot {class_name} key {key!r}"
                )
            result[key] = json.loads(match.group("display"))
        return result

    @classmethod
    def _parse_groups(
        cls,
        payload: bytes,
        collections: dict[str, str],
    ) -> dict[str, str]:
        groups: dict[str, str] = {}
        for line in cls._enum_constant_lines(payload, _GROUP_MODEL_PATH, "OmGroup"):
            match = _GROUP_ENTRY_RE.fullmatch(line)
            if match is None:
                raise LeaderboardBotDataError(
                    "unparsed OmGroup data in leaderboard-bot source"
                )
            key = match.group("key")
            source_collection = match.group("collection")
            if key in groups:
                raise LeaderboardBotDataError(
                    f"duplicate leaderboard-bot OmGroup key {key!r}"
                )
            if source_collection not in collections:
                raise LeaderboardBotDataError(
                    f"leaderboard-bot group {key!r} references unknown collection "
                    f"{source_collection!r}"
                )
            groups[key] = source_collection
        return groups

    @classmethod
    def _parse_puzzles(
        cls,
        payload: bytes,
        groups: dict[str, str],
        types: dict[str, str],
    ) -> dict[str, _UpstreamPuzzle]:
        by_game_id: dict[str, _UpstreamPuzzle] = {}
        leaderboard_keys: set[str] = set()
        for line in cls._enum_constant_lines(payload, _PUZZLE_MODEL_PATH, "OmPuzzle"):
            match = _PUZZLE_ENTRY_RE.fullmatch(line)
            if match is None:
                raise LeaderboardBotDataError(
                    "unparsed OmPuzzle data in leaderboard-bot source"
                )
            leaderboard_key = match.group("key")
            group_key = match.group("group")
            type_key = match.group("type")
            game_puzzle_id = json.loads(match.group("id"))
            if leaderboard_key in leaderboard_keys:
                raise LeaderboardBotDataError(
                    f"duplicate leaderboard key {leaderboard_key!r} in leaderboard-bot"
                )
            if game_puzzle_id in by_game_id:
                raise LeaderboardBotDataError(
                    f"duplicate game puzzle id {game_puzzle_id!r} in leaderboard-bot"
                )
            if group_key not in groups:
                raise LeaderboardBotDataError(
                    f"leaderboard-bot puzzle {leaderboard_key!r} references unknown group "
                    f"{group_key!r}"
                )
            if type_key not in types:
                raise LeaderboardBotDataError(
                    f"leaderboard-bot puzzle {leaderboard_key!r} references unknown type "
                    f"{type_key!r}"
                )
            leaderboard_keys.add(leaderboard_key)
            by_game_id[game_puzzle_id] = _UpstreamPuzzle(
                leaderboard_key=leaderboard_key,
                game_puzzle_id=game_puzzle_id,
                display_name=json.loads(match.group("display")),
                group_key=group_key,
                type_key=type_key,
            )
        return by_game_id

    @staticmethod
    def _canonical_group(group_key: str, collection_key: str) -> str:
        if collection_key == "CAMPAIGN":
            if group_key == "CHAPTER_PRODUCTION":
                return "appendix"
            match = re.fullmatch(r"CHAPTER_([1-9][0-9]*)", group_key)
            if match:
                return f"chapter-{match.group(1)}"
        elif collection_key == "JOURNAL_XCIX":
            match = re.fullmatch(r"JOURNAL_([IVXLCDM]+)", group_key)
            if match:
                return f"journal-xcix-{match.group(1).lower()}"
        elif collection_key == "JOURNAL_CVIII":
            match = re.fullmatch(r"JOURNAL_CVIII_([IVXLCDM]+)", group_key)
            if match:
                return f"journal-cviii-{match.group(1).lower()}"
        raise LeaderboardBotDataError(
            f"unsupported leaderboard-bot group {group_key!r} in collection {collection_key!r}"
        )

    @staticmethod
    def _canonical_kind(group_key: str, collection_key: str) -> str:
        if collection_key == "CAMPAIGN":
            return "production" if group_key == "CHAPTER_PRODUCTION" else "campaign"
        if collection_key in {"JOURNAL_XCIX", "JOURNAL_CVIII"}:
            return "journal"
        raise LeaderboardBotDataError(
            f"unsupported leaderboard-bot collection {collection_key!r}"
        )
