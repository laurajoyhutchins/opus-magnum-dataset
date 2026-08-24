from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from opus_corpus.adapters import (
    ADAPTERS,
    AdapterDataError,
    AdapterFetchError,
    AdapterNotImplementedError,
    GitHubSourceAdapter,
    LeaderboardPuzzle,
    SourceAdapter,
)
from opus_corpus.collections import CollectionDefinition

EXPECTED_REVISIONS = {
    "leaderboard-bot": "ca40dee95da584270eb3be1c4b74e2be63afa7e6",
    "om-archive": "44006a0eeb0051337640443d1b0576ea24c983f6",
    "om-leaderboard": "0cfd371ef66cf94eac3f7a7a06bc9ab959495576",
    "omsim": "758f4a4b4c9e24f50294801da774a0960c922bab",
    "molecule-db": "6f3cd8068428ef96ac6426d092c3523da359ec76",
    "official-game": None,
}

EXPECTED_REPOSITORIES = {
    "leaderboard-bot": "F43nd1r/zachtronics-leaderboard-bot",
    "om-archive": "F43nd1r/om-archive",
    "om-leaderboard": "F43nd1r/om-leaderboard",
    "omsim": "ianh/omsim",
    "molecule-db": "fenhl/molecule-db",
}


def _collection(
    tmp_path: Path,
    rows: tuple[dict[str, str], ...] = (),
) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="test-collection",
        inventory_sha256="0" * 64,
        puzzle_count=len(rows),
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=rows,
        manifest={},
    )


def _archive_bytes(root: str, files: dict[str, bytes]) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for relative_path, contents in files.items():
            info = tarfile.TarInfo(f"{root}/{relative_path}")
            info.size = len(contents)
            archive.addfile(info, io.BytesIO(contents))
    return payload.getvalue()


def _leaderboard_source(tmp_path: Path, entries: str) -> Path:
    source_root = tmp_path / "leaderboard-source"
    model_path = source_root / (
        "src/main/kotlin/com/faendir/zachtronics/bot/om/model/OmPuzzle.kt"
    )
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        "enum class OmPuzzle {\n" + entries + "\n    ;\n}\n",
        encoding="utf-8",
    )
    return source_root


def _inventory_row(
    puzzle_id: str,
    display_name: str,
    kind: str,
    group: str,
    game_puzzle_id: str,
    leaderboard_key: str,
    puzzle_type: str,
) -> dict[str, str]:
    return {
        "puzzle_id": puzzle_id,
        "display_name": display_name,
        "kind": kind,
        "group": group,
        "game_puzzle_id": game_puzzle_id,
        "leaderboard_key": leaderboard_key,
        "puzzle_type": puzzle_type,
    }


def test_adapter_registry_has_expected_sources_and_revisions():
    assert set(ADAPTERS) == set(EXPECTED_REVISIONS)
    assert {
        source_id: adapter_type.pinned_revision for source_id, adapter_type in ADAPTERS.items()
    } == EXPECTED_REVISIONS


def test_registered_adapters_derive_from_source_adapter():
    assert all(issubclass(adapter_type, SourceAdapter) for adapter_type in ADAPTERS.values())


def test_github_adapters_declare_repository_identity():
    assert {
        source_id: adapter_type.repository
        for source_id, adapter_type in ADAPTERS.items()
        if issubclass(adapter_type, GitHubSourceAdapter)
    } == EXPECTED_REPOSITORIES


@pytest.mark.parametrize("source_id", sorted(EXPECTED_REPOSITORIES))
def test_github_fetch_materializes_pinned_archive_once(source_id: str, tmp_path: Path):
    adapter_type = ADAPTERS[source_id]
    revision = EXPECTED_REVISIONS[source_id]
    assert revision is not None

    calls: list[str] = []

    def download(url: str) -> bytes:
        calls.append(url)
        return _archive_bytes("source-root", {"nested/source.txt": source_id.encode()})

    adapter = adapter_type(download=download)
    cache_root = tmp_path / "cache"

    first = adapter.fetch(_collection(tmp_path), cache_root)
    second = adapter.fetch(_collection(tmp_path), cache_root)

    expected_url = (
        f"https://codeload.github.com/{EXPECTED_REPOSITORIES[source_id]}/tar.gz/{revision}"
    )
    assert calls == [expected_url]
    assert first == second == cache_root / source_id / revision
    assert (first / "nested/source.txt").read_text() == source_id


def test_github_fetch_failure_does_not_create_cache_entry(tmp_path: Path):
    adapter_type = ADAPTERS["leaderboard-bot"]
    revision = EXPECTED_REVISIONS["leaderboard-bot"]
    assert revision is not None

    adapter = adapter_type(download=lambda _url: b"not a tar archive")
    cache_root = tmp_path / "cache"
    target = cache_root / "leaderboard-bot" / revision

    with pytest.raises(AdapterFetchError, match="leaderboard-bot"):
        adapter.fetch(_collection(tmp_path), cache_root)

    assert not target.exists()


def test_leaderboard_bot_load_catalog_parses_active_enum_entries(tmp_path: Path):
    source_root = _leaderboard_source(
        tmp_path,
        """
    STABILIZED_WATER(CHAPTER_1, NORMAL, "Stabilized Water", "P007"),
    // RETIRED_PUZZLE(CHAPTER_1, NORMAL, "Retired Puzzle", "P999"),
    MATERIAL_SALVAGE(
        TOURNAMENT_2025,
        NORMAL,
        "Material Salvage",
        "w3446276940",
        "OM2025_break_Material Salvage",
    ),
""",
    )

    catalog = ADAPTERS["leaderboard-bot"]().load_catalog(source_root)

    assert catalog["STABILIZED_WATER"] == LeaderboardPuzzle(
        leaderboard_key="STABILIZED_WATER",
        group_key="CHAPTER_1",
        puzzle_type="normal",
        display_name="Stabilized Water",
        game_puzzle_id="P007",
        alt_ids=(),
    )
    assert catalog["MATERIAL_SALVAGE"].alt_ids == ("OM2025_break_Material Salvage",)
    assert "RETIRED_PUZZLE" not in catalog


def test_leaderboard_bot_reconciles_collection_in_canonical_order(tmp_path: Path):
    source_root = _leaderboard_source(
        tmp_path,
        """
    STABILIZED_WATER(CHAPTER_1, NORMAL, "Stabilized Water", "P007"),
    SILVER_PAINT(CHAPTER_PRODUCTION, PRODUCTION, "Silver Paint", "P076"),
    VAN_BERLO_S_WHEEL(JOURNAL_I, NORMAL, "Van Berlo's Wheel", "P054"),
    DIFFUSIVE_GOLD(JOURNAL_CVIII_XII, NORMAL, "Diffusive Gold", "P318"),
""",
    )
    rows = (
        _inventory_row(
            "om.puzzle.0001",
            "Stabilized Water",
            "campaign",
            "chapter-1",
            "P007",
            "STABILIZED_WATER",
            "normal",
        ),
        _inventory_row(
            "om.puzzle.0002",
            "Silver Paint",
            "production",
            "appendix",
            "P076",
            "SILVER_PAINT",
            "production",
        ),
        _inventory_row(
            "om.puzzle.0003",
            "Van Berlo's Wheel",
            "journal",
            "journal-xcix-i",
            "P054",
            "VAN_BERLO_S_WHEEL",
            "normal",
        ),
        _inventory_row(
            "om.puzzle.0004",
            "Diffusive Gold",
            "journal",
            "journal-cviii-xii",
            "P318",
            "DIFFUSIVE_GOLD",
            "normal",
        ),
    )

    reconciled = ADAPTERS["leaderboard-bot"]().reconcile_collection(
        _collection(tmp_path, rows),
        source_root,
    )

    assert tuple(puzzle.leaderboard_key for puzzle in reconciled) == tuple(
        row["leaderboard_key"] for row in rows
    )


def test_leaderboard_bot_reconciliation_fails_closed_on_identity_drift(tmp_path: Path):
    source_root = _leaderboard_source(
        tmp_path,
        '    STABILIZED_WATER(CHAPTER_1, NORMAL, "Stabilized Water", "P007"),',
    )
    rows = (
        _inventory_row(
            "om.puzzle.0001",
            "Stabilized Water",
            "campaign",
            "chapter-1",
            "P999",
            "STABILIZED_WATER",
            "normal",
        ),
    )

    with pytest.raises(AdapterDataError, match="game_puzzle_id"):
        ADAPTERS["leaderboard-bot"]().reconcile_collection(
            _collection(tmp_path, rows),
            source_root,
        )


def test_official_game_fetch_still_fails_closed(tmp_path: Path):
    adapter = ADAPTERS["official-game"]()
    with pytest.raises(AdapterNotImplementedError, match="official-game"):
        adapter.fetch(_collection(tmp_path), tmp_path / "cache")
