from .github import GitHubSourceAdapter


class OmsimAdapter(GitHubSourceAdapter):
    source_id = "omsim"
    pinned_revision = "758f4a4b4c9e24f50294801da774a0960c922bab"
    repository = "ianh/omsim"
