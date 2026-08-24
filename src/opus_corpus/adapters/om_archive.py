from __future__ import annotations

from pathlib import Path, PurePosixPath

from ..cache import ContentAddressedCache
from ..collections import CollectionDefinition
from ..github_source import iter_github_tarball_members
from ..solution_sources import OM_ARCHIVE_SOURCE
from .base import AcquisitionResult, SourceAdapter


class OmArchiveAdapter(SourceAdapter):
    source_layout = OM_ARCHIVE_SOURCE
    source_id = source_layout.source_id
    pinned_revision = source_layout.pinned_revision

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> AcquisitionResult:
        expected_directories = self._expected_directories(collection)
        cache = ContentAddressedCache(cache_root)
        covered: set[str] = set()
        candidate_count = 0

        for upstream_path, member in iter_github_tarball_members(
            "F43nd1r",
            "om-archive",
            self.pinned_revision,
        ):
            path = PurePosixPath(upstream_path)
            if path.suffix != ".solution":
                continue
            puzzle_id = expected_directories.get(path.parent.as_posix())
            if puzzle_id is None:
                continue
            cache.put_bytes(
                self.source_id,
                self.pinned_revision,
                upstream_path,
                member.read(),
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
        return OM_ARCHIVE_SOURCE.expected_directories(collection)
