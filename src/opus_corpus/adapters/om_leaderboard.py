from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import AdapterDataError
from .github import GitHubSourceAdapter
from .leaderboard_bot import LeaderboardPuzzle


@dataclass(frozen=True)
class OmLeaderboardCandidate:
    solution_path: Path
    metadata_path: Path | None
    claimed_cost: int | None
    claimed_cycles: int | None
    claimed_area: int | None
    claimed_instructions: int | None
    display_link: str | None
    data_link: str | None
    last_modified: str | None


class OmLeaderboardAdapter(GitHubSourceAdapter):
    source_id = "om-leaderboard"
    pinned_revision = "0cfd371ef66cf94eac3f7a7a06bc9ab959495576"
    repository = "F43nd1r/om-leaderboard"

    def solution_candidates(
        self,
        source_root: Path,
        puzzle: LeaderboardPuzzle,
    ) -> tuple[OmLeaderboardCandidate, ...]:
        """Enumerate solutions and validate any adjacent source observation metadata."""
        directory = source_root / puzzle.group_key / puzzle.leaderboard_key
        if not directory.exists():
            return ()
        if not directory.is_dir():
            raise AdapterDataError(
                f"source adapter {self.source_id!r} expected directory {directory}"
            )

        candidates: list[OmLeaderboardCandidate] = []
        for solution_path in sorted(directory.glob("*.solution")):
            if not solution_path.is_file():
                continue
            metadata_path = solution_path.with_suffix(".json")
            if not metadata_path.is_file():
                candidates.append(
                    OmLeaderboardCandidate(
                        solution_path=solution_path,
                        metadata_path=None,
                        claimed_cost=None,
                        claimed_cycles=None,
                        claimed_area=None,
                        claimed_instructions=None,
                        display_link=None,
                        data_link=None,
                        last_modified=None,
                    )
                )
                continue
            candidates.append(
                self._candidate_from_metadata(
                    source_root,
                    puzzle,
                    solution_path,
                    metadata_path,
                )
            )
        return tuple(candidates)

    def _candidate_from_metadata(
        self,
        source_root: Path,
        puzzle: LeaderboardPuzzle,
        solution_path: Path,
        metadata_path: Path,
    ) -> OmLeaderboardCandidate:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} could not parse {metadata_path}"
            ) from exc
        if not isinstance(metadata, dict):
            raise AdapterDataError(
                f"source adapter {self.source_id!r} expected object metadata at {metadata_path}"
            )

        if metadata.get("puzzle") != puzzle.leaderboard_key:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} metadata puzzle mismatch at {metadata_path}"
            )
        expected_data_path = solution_path.relative_to(source_root).as_posix()
        if metadata.get("dataPath") != expected_data_path:
            raise AdapterDataError(
                f"source adapter {self.source_id!r} dataPath mismatch at {metadata_path}: "
                f"expected {expected_data_path!r}, observed {metadata.get('dataPath')!r}"
            )

        score = metadata.get("score")
        if not isinstance(score, dict):
            raise AdapterDataError(
                f"source adapter {self.source_id!r} expected score object at {metadata_path}"
            )

        return OmLeaderboardCandidate(
            solution_path=solution_path,
            metadata_path=metadata_path,
            claimed_cost=self._optional_int(score, "cost", metadata_path),
            claimed_cycles=self._optional_int(score, "cycles", metadata_path),
            claimed_area=self._optional_int(score, "area", metadata_path),
            claimed_instructions=self._optional_int(score, "instructions", metadata_path),
            display_link=self._optional_string(metadata, "displayLink", metadata_path),
            data_link=self._optional_string(metadata, "dataLink", metadata_path),
            last_modified=self._optional_string(metadata, "lastModified", metadata_path),
        )

    def _optional_int(self, value: dict[str, Any], key: str, path: Path) -> int | None:
        item = value.get(key)
        if item is None:
            return None
        if isinstance(item, bool) or not isinstance(item, int):
            raise AdapterDataError(
                f"source adapter {self.source_id!r} expected integer {key!r} at {path}"
            )
        return item

    def _optional_string(
        self,
        value: dict[str, Any],
        key: str,
        path: Path,
    ) -> str | None:
        item = value.get(key)
        if item is None:
            return None
        if not isinstance(item, str):
            raise AdapterDataError(
                f"source adapter {self.source_id!r} expected string {key!r} at {path}"
            )
        return item
