from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..collections import CollectionDefinition
from .base import AdapterDataError
from .github import GitHubSourceAdapter

_PUZZLE_MODEL_PATH = Path(
    "src/main/kotlin/com/faendir/zachtronics/bot/om/model/OmPuzzle.kt"
)
_QUOTED_STRING = r'"(?:\\.|[^"\\])*"'
_ENTRY_RE = re.compile(
    rf"(?m)^\s*(?P<key>[A-Z][A-Z0-9_]*)\s*\(\s*"
    rf"(?P<group>[A-Z][A-Z0-9_]*)\s*,\s*"
    rf"(?P<type>[A-Z][A-Z0-9_]*)\s*,\s*"
    rf"(?P<display>{_QUOTED_STRING})\s*,\s*"
    rf"(?P<id>{_QUOTED_STRING})"
    rf"(?P<alts>(?:\s*,\s*{_QUOTED_STRING})*)\s*,?\s*"
    rf"\)\s*,?\s*$"
)
_STRING_RE = re.compile(_QUOTED_STRING)
_ENUM_END_RE = re.compile(r"(?m)^\s*;\s*$")


@dataclass(frozen=True)
class LeaderboardPuzzle:
    leaderboard_key: str
    group_key: str
    puzzle_type: str
    display_name: str
    game_puzzle_id: str
    alt_ids: tuple[str, ...]

    @property
    def collection_group(self) -> str:
        group = self.group_key
        if re.fullmatch(r"CHAPTER_[1-5]", group):
            return f"chapter-{group.removeprefix('CHAPTER_')}"
        if group == "CHAPTER_PRODUCTION":
            return "appendix"
        if group.startswith("JOURNAL_CVIII_"):
            return f"journal-cviii-{group.removeprefix('JOURNAL_CVIII_').lower()}"
        if group.startswith("JOURNAL_"):
            return f"journal-xcix-{group.removeprefix('JOURNAL_').lower()}"
        if group.startswith("DRM_CHAPTER_"):
            return f"drm-chapter-{group.removeprefix('DRM_CHAPTER_').lower()}"
        if group.startswith("TOURNAMENT_"):
            return f"tournament-{group.removeprefix('TOURNAMENT_').lower()}"
        if group.startswith("WEEKLIES_"):
            return f"weeklies-{group.removeprefix('WEEKLIES_').lower()}"
        raise AdapterDataError(f"unsupported leaderboard group {group!r}")

    @property
    def collection_kind(self) -> str:
        group = self.group_key
        if re.fullmatch(r"CHAPTER_[1-5]", group):
            return "campaign"
        if group == "CHAPTER_PRODUCTION":
            return "production"
        if group.startswith("JOURNAL_"):
            return "journal"
        if group.startswith("DRM_CHAPTER_"):
            return "expansion"
        if group.startswith("TOURNAMENT_"):
            return "tournament"
        if group.startswith("WEEKLIES_"):
            return "custom"
        raise AdapterDataError(f"unsupported leaderboard group {group!r}")


class LeaderboardBotAdapter(GitHubSourceAdapter):
    source_id = "leaderboard-bot"
    pinned_revision = "ca40dee95da584270eb3be1c4b74e2be63afa7e6"
    repository = "F43nd1r/zachtronics-leaderboard-bot"

    def load_catalog(self, source_root: Path) -> dict[str, LeaderboardPuzzle]:
        """Parse the pinned Opus Magnum puzzle enum into upstream identity facts."""
        model_path = source_root / _PUZZLE_MODEL_PATH
        try:
            text = model_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} could not read {model_path}"
            ) from exc

        enum_marker = "enum class OmPuzzle"
        marker_offset = text.find(enum_marker)
        brace_offset = text.find("{", marker_offset)
        if marker_offset < 0 or brace_offset < 0:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} could not locate OmPuzzle enum body"
            )
        end_match = _ENUM_END_RE.search(text, brace_offset + 1)
        if end_match is None:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} could not locate OmPuzzle enum terminator"
            )

        body = text[brace_offset + 1 : end_match.start()]
        body = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("//")
        )
        matches = list(_ENTRY_RE.finditer(body))
        remainder = _ENTRY_RE.sub("", body).strip()
        if remainder:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} encountered unparsed OmPuzzle enum data"
            )
        if not matches:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} found no active OmPuzzle entries"
            )

        catalog: dict[str, LeaderboardPuzzle] = {}
        for match in matches:
            key = match.group("key")
            if key in catalog:
                raise AdapterDataError(
                    f"source adapter {self.source_id!r} found duplicate puzzle key {key!r}"
                )
            catalog[key] = LeaderboardPuzzle(
                leaderboard_key=key,
                group_key=match.group("group"),
                puzzle_type=match.group("type").lower(),
                display_name=json.loads(match.group("display")),
                game_puzzle_id=json.loads(match.group("id")),
                alt_ids=tuple(
                    json.loads(value) for value in _STRING_RE.findall(match.group("alts"))
                ),
            )
        return catalog

    def reconcile_collection(
        self,
        collection: CollectionDefinition,
        source_root: Path,
    ) -> tuple[LeaderboardPuzzle, ...]:
        """Verify source-backed identity fields without mutating canonical membership."""
        catalog = self.load_catalog(source_root)
        reconciled: list[LeaderboardPuzzle] = []
        errors: list[str] = []
        fields = (
            "display_name",
            "kind",
            "group",
            "game_puzzle_id",
            "leaderboard_key",
            "puzzle_type",
        )

        for row in collection.inventory_rows:
            key = row["leaderboard_key"]
            puzzle = catalog.get(key)
            if puzzle is None:
                errors.append(f"{key}: missing from pinned puzzle model")
                continue
            observed = {
                "display_name": puzzle.display_name,
                "kind": puzzle.collection_kind,
                "group": puzzle.collection_group,
                "game_puzzle_id": puzzle.game_puzzle_id,
                "leaderboard_key": puzzle.leaderboard_key,
                "puzzle_type": puzzle.puzzle_type,
            }
            for field in fields:
                if row[field] != observed[field]:
                    errors.append(
                        f"{key}: {field} expected {row[field]!r}, observed {observed[field]!r}"
                    )
            reconciled.append(puzzle)

        if errors:
            details = "; ".join(errors)
            raise AdapterDataError(
                f"source adapter {self.source_id!r} does not reconcile with "
                f"collection {collection.collection_id!r}: {details}"
            )
        return tuple(reconciled)
