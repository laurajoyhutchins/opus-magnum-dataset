from __future__ import annotations

from pathlib import Path, PurePosixPath

from ..cache import ContentAddressedCache
from ..collections import CollectionDefinition
from ..github_source import AcquisitionError, download_github_tarball, tarball_files
from .base import AcquisitionResult, SourceAdapter


class OmsimAdapter(SourceAdapter):
    source_id = "omsim"
    pinned_revision = "758f4a4b4c9e24f50294801da774a0960c922bab"

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> AcquisitionResult:
        tarball = download_github_tarball("ianh", "omsim", self.pinned_revision)
        files = tarball_files(tarball, suffix=".puzzle")
        expected = {
            row["game_puzzle_id"]: row["puzzle_id"]
            for row in collection.inventory_rows
            if row["kind"] == "campaign"
        }
        matches: dict[str, tuple[str, str, bytes]] = {}

        for upstream_path, payload in files.items():
            path = PurePosixPath(upstream_path)
            if path.parts[:3] != ("test", "puzzle", "campaign"):
                continue
            game_puzzle_id = path.stem
            puzzle_id = expected.get(game_puzzle_id)
            if puzzle_id is None:
                continue
            if game_puzzle_id in matches:
                first_path = matches[game_puzzle_id][1]
                raise AcquisitionError(
                    f"omsim found multiple campaign fixtures for {game_puzzle_id}: "
                    f"{first_path}, {upstream_path}"
                )
            matches[game_puzzle_id] = (puzzle_id, upstream_path, payload)

        cache = ContentAddressedCache(cache_root)
        covered: set[str] = set()
        for game_puzzle_id in sorted(matches):
            puzzle_id, upstream_path, payload = matches[game_puzzle_id]
            cache.put_bytes(
                self.source_id,
                self.pinned_revision,
                upstream_path,
                payload,
                rights_status="local_fetch_only",
            )
            covered.add(puzzle_id)

        return AcquisitionResult(
            source_id=self.source_id,
            candidate_count=len(matches),
            puzzles_covered=len(covered),
        )
