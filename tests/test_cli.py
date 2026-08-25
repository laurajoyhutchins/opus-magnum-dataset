from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import opus_corpus.v1_release as v1_release
from opus_corpus.adapters.base import AcquisitionResult
from opus_corpus.adapters.leaderboard_bot import LeaderboardBotAdapter
from opus_corpus.adapters.official_game import OfficialGameAdapter
from opus_corpus.adapters.om_archive import OmArchiveAdapter
from opus_corpus.cli import main
from opus_corpus.libverify import LibverifyVerifier

HEADER = "puzzle_id,display_name,kind,group,game_puzzle_id,leaderboard_key,puzzle_type\n"
ROW = "om.puzzle.0001,One,campaign,chapter-1,P001,ONE,normal\n"


def write_collection(tmp_path: Path) -> Path:
    inventory = tmp_path / "fixture.csv"
    inventory.write_text(HEADER + ROW, encoding="utf-8")
    digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
    manifest = tmp_path / "fixture.toml"
    manifest.write_text(
        f'''schema_version = 1
collection_id = "fixture-2026-08-23"
title = "Fixture"
effective_date = "2026-08-23"
status = "frozen"
puzzle_count = 1
inventory_file = "fixture.csv"
inventory_sha256 = "{digest}"
scope = "Synthetic fixture"
excludes = []
[membership_source]
source = "example/source"
revision = "abc"
puzzle_model = "Puzzle"
group_model = "Group"
collection_model = "Collection"
[release_evidence]
journal_final_issue_date = "2026-06-16"
journal_issue_count = 24
source_url = "https://example.invalid/"
[group_counts]
chapter_1 = 1
''',
        encoding="utf-8",
    )
    return manifest


def test_collections_validate_explicit_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    manifest = write_collection(tmp_path)
    assert main(["collections", "validate", str(manifest)]) == 0
    assert "fixture-2026-08-23" in capsys.readouterr().out


def test_collection_validation_failure_returns_one(tmp_path: Path):
    manifest = write_collection(tmp_path)
    (tmp_path / "fixture.csv").write_text(HEADER + ROW + "\n", encoding="utf-8")
    assert main(["collections", "validate", str(manifest)]) == 1


def test_fetch_selected_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    root = Path(__file__).resolve().parents[1]
    config = root / "corpus.toml"
    cache = tmp_path / "cache"

    def fake_fetch(self, collection, cache_root):
        assert collection.collection_id == "base-game-2026-06-16"
        assert cache_root == cache
        return AcquisitionResult(
            source_id="om-archive",
            candidate_count=2,
            puzzles_covered=1,
        )

    monkeypatch.setattr(OmArchiveAdapter, "fetch", fake_fetch)

    assert (
        main(
            [
                "--config",
                str(config),
                "fetch",
                "base-game-2026-06-16",
                "--source",
                "om-archive",
                "--cache",
                str(cache),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "om-archive" in output
    assert "2 candidates" in output
    assert "1 puzzles" in output


def test_fetch_leaderboard_bot_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    root = Path(__file__).resolve().parents[1]
    config = root / "corpus.toml"
    cache = tmp_path / "cache"

    def fake_fetch(self, collection, cache_root):
        assert collection.collection_id == "base-game-2026-06-16"
        assert cache_root == cache
        return AcquisitionResult(
            source_id="leaderboard-bot",
            candidate_count=4,
            puzzles_covered=166,
        )

    monkeypatch.setattr(LeaderboardBotAdapter, "fetch", fake_fetch)

    assert (
        main(
            [
                "--config",
                str(config),
                "fetch",
                "base-game-2026-06-16",
                "--source",
                "leaderboard-bot",
                "--cache",
                str(cache),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "leaderboard-bot" in output
    assert "4 candidates" in output
    assert "166 puzzles" in output


def test_fetch_official_game_requires_explicit_source_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    root = Path(__file__).resolve().parents[1]
    config = root / "corpus.toml"

    assert (
        main(
            [
                "--config",
                str(config),
                "fetch",
                "base-game-2026-06-16",
                "--source",
                "official-game",
                "--cache",
                str(tmp_path / "cache"),
            ]
        )
        == 2
    )
    assert "--source-root" in capsys.readouterr().err


def test_fetch_official_game_passes_explicit_source_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    root = Path(__file__).resolve().parents[1]
    config = root / "corpus.toml"
    cache = tmp_path / "cache"
    source_root = tmp_path / "official"

    def fake_fetch(self, collection, cache_root):
        assert self.source_root == source_root
        assert collection.collection_id == "base-game-2026-06-16"
        assert cache_root == cache
        return AcquisitionResult(
            source_id="official-game",
            candidate_count=1,
            puzzles_covered=1,
        )

    monkeypatch.setattr(OfficialGameAdapter, "fetch", fake_fetch)

    assert (
        main(
            [
                "--config",
                str(config),
                "fetch",
                "base-game-2026-06-16",
                "--source",
                "official-game",
                "--cache",
                str(cache),
                "--source-root",
                str(source_root),
            ]
        )
        == 0
    )
    assert "official-game" in capsys.readouterr().out


def test_release_v1_wires_pinned_verifier_and_offline_builder(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    config_path = root / "corpus.toml"
    cache = tmp_path / "cache"
    output = tmp_path / "release"
    library = tmp_path / "libverify.so"
    expected_sha256 = "d" * 64
    fixture_verifier = object()

    def fake_from_library(cls, path: Path, *, expected_sha256: str):
        assert cls is LibverifyVerifier
        assert Path(path) == library
        assert expected_sha256 == "d" * 64
        return fixture_verifier

    def fake_build_v1_release(
        collection,
        *,
        cache_root: Path,
        output_dir: Path,
        config,
        verifier,
        payload_policy: str,
    ):
        assert collection.collection_id == "base-game-2026-06-16"
        assert cache_root == cache
        assert output_dir == output
        assert verifier is fixture_verifier
        assert payload_policy == "metadata-only"
        assert config.path == config_path
        return SimpleNamespace(
            collection_id=collection.collection_id,
            split="base_game_2026_06_16",
            logical_release_sha256="e" * 64,
        )

    monkeypatch.setattr(
        LibverifyVerifier,
        "from_library",
        classmethod(fake_from_library),
    )
    monkeypatch.setattr(v1_release, "build_v1_release", fake_build_v1_release)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "release",
                "v1",
                "base-game-2026-06-16",
                "--cache",
                str(cache),
                "--output",
                str(output),
                "--libverify",
                str(library),
                "--libverify-sha256",
                expected_sha256,
            ]
        )
        == 0
    )
    rendered = capsys.readouterr().out
    assert "base-game-2026-06-16" in rendered
    assert "e" * 64 in rendered


def test_tiny_fixture_end_to_end_when_pyarrow_and_repo_collection_are_present(tmp_path: Path):
    pytest.importorskip("pyarrow")
    root = Path(__file__).resolve().parents[1]
    if not (root / "collections/base-game-2026-06-16.toml").exists():
        pytest.skip("connector-backed local mirror does not include committed collection files")
    output = tmp_path / "release"
    stage = tmp_path / "stage"
    config = root / "corpus.toml"
    assert main(["--config", str(config), "collections", "validate"]) == 0
    assert (
        main(
            [
                "--config",
                str(config),
                "release",
                "build",
                "base-game-2026-06-16",
                "--input",
                str(root / "fixtures/tiny-corpus"),
                "--output",
                str(output),
                "--payload-policy",
                "metadata-only",
                "--coverage-policy",
                "subset",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--config",
                str(config),
                "release",
                "validate",
                "base-game-2026-06-16",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--config",
                str(config),
                "release",
                "stage",
                "base-game-2026-06-16",
                "--output",
                str(output),
                "--destination",
                str(stage),
            ]
        )
        == 0
    )
    files = {
        path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()
    }
    assert files == {
        "README.md",
        "LICENSE",
        "release-manifest.json",
        "data/puzzles/base_game_2026_06_16-00000-of-00001.parquet",
        "data/solutions/base_game_2026_06_16-00000-of-00001.parquet",
        "data/observations/base_game_2026_06_16-00000-of-00001.parquet",
        "data/normalized/base_game_2026_06_16-00000-of-00001.parquet",
    }
