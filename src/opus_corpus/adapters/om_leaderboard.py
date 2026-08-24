from .github import GitHubSourceAdapter


class OmLeaderboardAdapter(GitHubSourceAdapter):
    source_id = "om-leaderboard"
    pinned_revision = "0cfd371ef66cf94eac3f7a7a06bc9ab959495576"
    repository = "F43nd1r/om-leaderboard"
