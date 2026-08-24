from __future__ import annotations

from pathlib import Path, PurePosixPath

from ..cache import ContentAddressedCache
from ..collections import CollectionDefinition
from ..github_source import download_github_tarball, tarball_files
from .base import AcquisitionResult, SourceAdapter

_GROUP_DIRECTORIES = {
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


class OmArchiveAdapter(SourceAdapter):
    source_id = "om-archive"
    pinned_revision = "44006a0eeb0051337640443d1b0576ea24c983f6"

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> AcquisitionResult:
        tarball = download_github_tarball(
            "F43nd1r",
            "om-archive",
            self.pinned_revision,
        )
        files = tarball_files(tarball, suffix=".solution")
        expected_directories = self._expected_directories(collection)
        cache = ContentAddressedCache(cache_root)
        covered: set[str] = set()
        candidate_count = 0

        for upstream_path, payload in files.items():
            parent = PurePosixPath(upstream_path).parent.as_posix()
            puzzle_id = expected_directories.get(parent)
            if puzzle_id is None:
                continue
            cache.put_bytes(
                self.source_id,
                self.pinned_revision,
                upstream_path,
                payload,
                rights_status="local_fetch_only",
            )
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
            upstream_group = _GROUP_DIRECTORIES.get(row["group"])
            if upstream_group is None:
                continue
            directory = f"{upstream_group}/{row['leaderboard_key']}"
            directories[directory] = row["puzzle_id"]
        return directories
