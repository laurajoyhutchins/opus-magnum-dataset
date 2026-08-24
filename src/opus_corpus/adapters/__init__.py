from .base import AdapterDataError, AdapterNotImplementedError, SourceAdapter
from .github import AdapterFetchError, GitHubSourceAdapter
from .leaderboard_bot import LeaderboardBotAdapter, LeaderboardPuzzle
from .molecule_db import MoleculeDbAdapter
from .official_game import OfficialGameAdapter
from .om_archive import OmArchiveAdapter
from .om_leaderboard import OmLeaderboardAdapter, OmLeaderboardCandidate
from .omsim import OmsimAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    adapter.source_id: adapter
    for adapter in (
        LeaderboardBotAdapter,
        MoleculeDbAdapter,
        OfficialGameAdapter,
        OmArchiveAdapter,
        OmLeaderboardAdapter,
        OmsimAdapter,
    )
}

__all__ = [
    "ADAPTERS",
    "AdapterDataError",
    "AdapterFetchError",
    "AdapterNotImplementedError",
    "GitHubSourceAdapter",
    "LeaderboardBotAdapter",
    "LeaderboardPuzzle",
    "MoleculeDbAdapter",
    "OfficialGameAdapter",
    "OmArchiveAdapter",
    "OmLeaderboardAdapter",
    "OmLeaderboardCandidate",
    "OmsimAdapter",
    "SourceAdapter",
]
