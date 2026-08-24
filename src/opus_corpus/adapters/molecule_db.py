from .github import GitHubSourceAdapter


class MoleculeDbAdapter(GitHubSourceAdapter):
    source_id = "molecule-db"
    pinned_revision = "6f3cd8068428ef96ac6426d092c3523da359ec76"
    repository = "fenhl/molecule-db"
