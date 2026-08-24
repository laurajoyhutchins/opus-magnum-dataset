from .base import AdapterNotImplementedError, SourceAdapter
from .github import AdapterFetchError, GitHubSourceAdapter
from .leaderboard_bot import LeaderboardBotAdapter
from .molecule_db import MoleculeDbAdapter
from .official_game import OfficialGameAdapter
from .om_archive import OmArchiveAdapter
from .om_leaderboard import OmLeaderboardAdapter
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
    "AdapterFetchError",
    "AdapterNotImplementedError",
    "GitHubSourceAdapter",
    "LeaderboardBotAdapter",
    "MoleculeDbAdapter",
    "OfficialGameAdapter",
    "OmArchiveAdapter",
    "OmLeaderboardAdapter",
    "OmsimAdapter",
    "SourceAdapter",
]
