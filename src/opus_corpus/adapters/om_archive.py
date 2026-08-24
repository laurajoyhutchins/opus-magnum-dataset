from .github import GitHubSourceAdapter


class OmArchiveAdapter(GitHubSourceAdapter):
    source_id = "om-archive"
    pinned_revision = "44006a0eeb0051337640443d1b0576ea24c983f6"
    repository = "F43nd1r/om-archive"
