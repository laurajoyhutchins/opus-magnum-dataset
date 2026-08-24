from __future__ import annotations

from pathlib import Path

from .base import AdapterDataError
from .github import GitHubSourceAdapter
from .leaderboard_bot import LeaderboardPuzzle


class OmArchiveAdapter(GitHubSourceAdapter):
    source_id = "om-archive"
    pinned_revision = "44006a0eeb0051337640443d1b0576ea24c983f6"
    repository = "F43nd1r/om-archive"

    def solution_paths(
        self,
        source_root: Path,
        puzzle: LeaderboardPuzzle,
    ) -> tuple[Path, ...]:
        """Enumerate executable solution payloads for one upstream puzzle identity."""
        directory = source_root / puzzle.group_key / puzzle.leaderboard_key
        if not directory.exists():
            return ()
        if not directory.is_dir():
            raise AdapterDataError(
                f"source adapter {self.source_id!r} expected directory {directory}"
            )
        return tuple(
            sorted(
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix == ".solution"
            )
        )
