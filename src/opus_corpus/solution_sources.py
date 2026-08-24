from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class CollectionInventory(Protocol):
    inventory_rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class SolutionSourceLayout:
    source_id: str
    pinned_revision: str
    group_directory: Callable[[str], str | None]

    def expected_directories(self, collection: CollectionInventory) -> dict[str, str]:
        directories: dict[str, str] = {}
        for row in collection.inventory_rows:
            upstream_group = self.group_directory(row["group"])
            if upstream_group is None:
                continue
            directories[f"{upstream_group}/{row['leaderboard_key']}"] = row["puzzle_id"]
        return directories


_ARCHIVE_GROUP_DIRECTORIES = {
    "chapter-1": "CHAPTER_1",
    "chapter-2": "CHAPTER_2",
    "chapter-3": "CHAPTER_3",
    "chapter-4": "CHAPTER_4",
    "chapter-5": "CHAPTER_5",
    "appendix": "CHAPTER_PRODUCTION",
    "journal-xcix-i": "JOURNAL_I",
    "journal-xcix-ii": "JOURNAL_II",
    "journal-xcix-iii": "JOURNAL_III",
    "journal-xcix-iv": "JOURNAL_IV",
    "journal-xcix-v": "JOURNAL_V",
    "journal-xcix-vi": "JOURNAL_VI",
    "journal-xcix-vii": "JOURNAL_VII",
    "journal-xcix-viii": "JOURNAL_VIII",
    "journal-xcix-ix": "JOURNAL_IX",
}
_LEADERBOARD_CAMPAIGN_GROUP_DIRECTORIES = {
    "chapter-1": "CHAPTER_1",
    "chapter-2": "CHAPTER_2",
    "chapter-3": "CHAPTER_3",
    "chapter-4": "CHAPTER_4",
    "chapter-5": "CHAPTER_5",
    "appendix": "CHAPTER_PRODUCTION",
}
_ROMAN_ISSUES = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}


def _archive_group_directory(group: str) -> str | None:
    return _ARCHIVE_GROUP_DIRECTORIES.get(group)


def _leaderboard_group_directory(group: str) -> str | None:
    campaign = _LEADERBOARD_CAMPAIGN_GROUP_DIRECTORIES.get(group)
    if campaign is not None:
        return campaign
    for prefix, journal in (("journal-xcix-", "JOURNAL"), ("journal-cviii-", "JOURNAL_CVIII")):
        if group.startswith(prefix):
            issue = group.removeprefix(prefix)
            if issue in _ROMAN_ISSUES:
                return f"{journal}_{issue.upper()}"
    return None


OM_ARCHIVE_SOURCE = SolutionSourceLayout(
    source_id="om-archive",
    pinned_revision="44006a0eeb0051337640443d1b0576ea24c983f6",
    group_directory=_archive_group_directory,
)
OM_LEADERBOARD_SOURCE = SolutionSourceLayout(
    source_id="om-leaderboard",
    pinned_revision="0cfd371ef66cf94eac3f7a7a06bc9ab959495576",
    group_directory=_leaderboard_group_directory,
)
