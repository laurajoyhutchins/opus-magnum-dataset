from __future__ import annotations

from pathlib import Path, PurePosixPath

from ..cache import ContentAddressedCache
from ..collections import CollectionDefinition
from ..github_source import download_github_tarball, tarball_files
from .base import AcquisitionResult, SourceAdapter

_CAMPAIGN_GROUP_DIRECTORIES = {
    "chapter-1": "CHAPTER_1",
    "chapter-2": "CHAPTER_2",
    "chapter-3": "CHAPTER_3",
    "chapter-4": "CHAPTER_4",
    "chapter-5": "CHAPTER_5",
    "appendix": "CHAPTER_PRODUCTION",
}
_ROMAN_ISSUES = {
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "vi",
    "vii",
    "viii",
    "ix",
    "x",
    "xi",
    "xii",
}


class OmLeaderboardAdapter(SourceAdapter):
    source_id = "om-leaderboard"
    pinned_revision = "0cfd371ef66cf94eac3f7a7a06bc9ab959495576"

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> AcquisitionResult:
        tarball = download_github_tarball(
            "F43nd1r",
            "om-leaderboard",
            self.pinned_revision,
        )
        files = tarball_files(tarball)
        expected_directories = self._expected_directories(collection)
        cache = ContentAddressedCache(cache_root)
        covered: set[str] = set()
        candidate_count = 0

        for upstream_path, payload in files.items():
            path = PurePosixPath(upstream_path)
            puzzle_id = expected_directories.get(path.parent.as_posix())
            if puzzle_id is None or path.suffix not in {".solution", ".json"}:
                continue

            cache.put_bytes(
                self.source_id,
                self.pinned_revision,
                upstream_path,
                payload,
                rights_status="local_fetch_only",
            )
            if path.suffix == ".solution":
                covered.add(puzzle_id)
                candidate_count += 1

        return AcquisitionResult(
            source_id=self.source_id,
            candidate_count=candidate_count,
            puzzles_covered=len(covered),
        )

    @staticmethod
    def _expected_directories(collection: CollectionDefinition) -> dict[str, str]:
        directories: dict[str, str] = {}
        for row in collection.inventory_rows:
            upstream_group = _group_directory(row["group"])
            if upstream_group is None:
                continue
            directory = f"{upstream_group}/{row['leaderboard_key']}"
            directories[directory] = row["puzzle_id"]
        return directories


def _group_directory(group: str) -> str | None:
    campaign = _CAMPAIGN_GROUP_DIRECTORIES.get(group)
    if campaign is not None:
        return campaign

    xcix_prefix = "journal-xcix-"
    if group.startswith(xcix_prefix):
        issue = group.removeprefix(xcix_prefix)
        if issue in _ROMAN_ISSUES:
            return f"JOURNAL_{issue.upper()}"

    cviii_prefix = "journal-cviii-"
    if group.startswith(cviii_prefix):
        issue = group.removeprefix(cviii_prefix)
        if issue in _ROMAN_ISSUES:
            return f"JOURNAL_CVIII_{issue.upper()}"

    return None
