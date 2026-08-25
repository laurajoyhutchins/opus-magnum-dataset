from opus_corpus.adapters import ADAPTERS, SourceAdapter

EXPECTED_REVISIONS = {
    "leaderboard-bot": "ca40dee95da584270eb3be1c4b74e2be63afa7e6",
    "om-archive": "44006a0eeb0051337640443d1b0576ea24c983f6",
    "om-leaderboard": "0cfd371ef66cf94eac3f7a7a06bc9ab959495576",
    "omsim": "758f4a4b4c9e24f50294801da774a0960c922bab",
    "molecule-db": "6f3cd8068428ef96ac6426d092c3523da359ec76",
    "official-game": None,
}


def test_adapter_registry_has_expected_sources_and_revisions():
    assert set(ADAPTERS) == set(EXPECTED_REVISIONS)
    assert {
        source_id: adapter_type.pinned_revision for source_id, adapter_type in ADAPTERS.items()
    } == EXPECTED_REVISIONS


def test_registered_adapters_derive_from_source_adapter():
    assert all(issubclass(adapter_type, SourceAdapter) for adapter_type in ADAPTERS.values())


def test_registered_adapters_implement_fetch():
    assert {
        source_id
        for source_id, adapter_type in ADAPTERS.items()
        if adapter_type.fetch is SourceAdapter.fetch
    } == set()
