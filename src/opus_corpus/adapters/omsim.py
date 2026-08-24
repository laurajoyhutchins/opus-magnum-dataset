from __future__ import annotations

from pathlib import Path

from .base import AdapterDataError
from .github import GitHubSourceAdapter
from .leaderboard_bot import LeaderboardPuzzle


class OmsimAdapter(GitHubSourceAdapter):
    source_id = "omsim"
    pinned_revision = "758f4a4b4c9e24f50294801da774a0960c922bab"
    repository = "ianh/omsim"

    def puzzle_path(
        self,
        source_root: Path,
        puzzle: LeaderboardPuzzle,
    ) -> Path | None:
        """Resolve a unique omsim puzzle fixture by upstream game puzzle ID."""
        puzzle_root = source_root / "test" / "puzzle"
        if not puzzle_root.exists():
            return None
        if not puzzle_root.is_dir():
            raise AdapterDataError(
                f"source adapter {self.source_id!r} expected directory {puzzle_root}"
            )

        matches = tuple(
            sorted(
                path
                for path in puzzle_root.rglob(f"{puzzle.game_puzzle_id}.puzzle")
                if path.is_file()
            )
        )
        if len(matches) > 1:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} found multiple fixtures for "
                f"{puzzle.game_puzzle_id!r}: {matches}"
            )
        return matches[0] if matches else None
