from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from opus_corpus.cli import main

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
        "release-manifest.json",
        "data/puzzles/base_game_2026_06_16-00000-of-00001.parquet",
        "data/solutions/base_game_2026_06_16-00000-of-00001.parquet",
        "data/observations/base_game_2026_06_16-00000-of-00001.parquet",
        "data/normalized/base_game_2026_06_16-00000-of-00001.parquet",
    }
