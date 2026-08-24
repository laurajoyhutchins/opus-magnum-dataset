from .github import GitHubSourceAdapter


class LeaderboardBotAdapter(GitHubSourceAdapter):
    source_id = "leaderboard-bot"
    pinned_revision = "ca40dee95da584270eb3be1c4b74e2be63afa7e6"
    repository = "F43nd1r/zachtronics-leaderboard-bot"
