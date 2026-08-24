from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from opus_corpus.collections import validate_collection
from opus_corpus.errors import CollectionValidationError

HEADER = "puzzle_id,display_name,kind,group,game_puzzle_id,leaderboard_key,puzzle_type\n"
ROWS = [
    "om.puzzle.0001,One,campaign,chapter-1,P001,ONE,normal\n",
    "om.puzzle.0002,Two,campaign,chapter-1,P002,TWO,normal\n",
]


def write_fixture(tmp_path: Path, rows: list[str] | None = None, header: str = HEADER) -> Path:
    rows = ROWS if rows is None else rows
    inventory = tmp_path / "fixture.csv"
    inventory.write_text(header + "".join(rows), encoding="utf-8")
    digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
    manifest = tmp_path / "fixture.toml"
    manifest.write_text(
        f'''schema_version = 1
collection_id = "fixture-2026-08-23"
title = "Fixture"
effective_date = "2026-08-23"
status = "frozen"
puzzle_count = {len(rows)}
inventory_file = "fixture.csv"
inventory_sha256 = "{digest}"
scope = "Synthetic fixture"
excludes = []

[membership_source]
source = "example/source"
revision = "abc123"
puzzle_model = "Puzzle"
group_model = "Group"
collection_model = "Collection"

[release_evidence]
journal_final_issue_date = "2026-06-16"
journal_issue_count = 24
source_url = "https://example.invalid/"

[group_counts]
chapter_1 = {len(rows)}
''',
        encoding="utf-8",
    )
    return manifest


def error_codes(exc: CollectionValidationError) -> set[str]:
    return {error.code for error in exc.errors}


def test_valid_fixture_returns_collection_definition(tmp_path: Path):
    manifest = write_fixture(tmp_path)
    result = validate_collection(manifest)
    assert result.collection_id == "fixture-2026-08-23"
    assert result.puzzle_count == 2
    assert [row["puzzle_id"] for row in result.inventory_rows] == [
        "om.puzzle.0001",
        "om.puzzle.0002",
    ]


def test_inventory_hash_drift_is_rejected(tmp_path: Path):
    manifest = write_fixture(tmp_path)
    (tmp_path / "fixture.csv").write_text(HEADER + "".join(ROWS) + "\n", encoding="utf-8")
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert "inventory_hash_mismatch" in error_codes(exc.value)


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([ROWS[0], ROWS[0]], "duplicate_puzzle_id"),
        (
            [ROWS[0], "om.puzzle.0002,Two,campaign,chapter-1,P001,TWO,normal\n"],
            "duplicate_game_puzzle_id",
        ),
        (
            [ROWS[0], "om.puzzle.0002,Two,campaign,chapter-1,P002,ONE,normal\n"],
            "duplicate_leaderboard_key",
        ),
        (
            [ROWS[0], "om.puzzle.0003,Three,campaign,chapter-1,P003,THREE,normal\n"],
            "puzzle_id_sequence_error",
        ),
        (
            [ROWS[0], "om.puzzle.0002,Two,campaign,Chapter-1,P002,TWO,normal\n"],
            "inventory_row_error",
        ),
        (
            [ROWS[0], "om.puzzle.0002,Two,campaign,chapter-1,P002,TWO,bogus\n"],
            "inventory_row_error",
        ),
    ],
)
def test_inventory_corruptions_are_rejected(tmp_path: Path, rows: list[str], expected: str):
    manifest = write_fixture(tmp_path, rows)
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert expected in error_codes(exc.value)


def test_exact_header_is_required(tmp_path: Path):
    manifest = write_fixture(
        tmp_path,
        header="display_name,puzzle_id,kind,group,game_puzzle_id,leaderboard_key,puzzle_type\n",
    )
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert "inventory_header_error" in error_codes(exc.value)


def test_row_count_mismatch_is_rejected(tmp_path: Path):
    manifest = write_fixture(tmp_path)
    text = manifest.read_text(encoding="utf-8").replace("puzzle_count = 2", "puzzle_count = 3")
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert "puzzle_count_mismatch" in error_codes(exc.value)


def test_group_rollup_unmatched_is_rejected(tmp_path: Path):
    manifest = write_fixture(tmp_path)
    text = manifest.read_text(encoding="utf-8").replace("chapter_1 = 2", "appendix = 2")
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert "group_rollup_unmatched" in error_codes(exc.value)


def test_group_rollup_overlap_is_rejected(tmp_path: Path):
    manifest = write_fixture(tmp_path)
    text = manifest.read_text(encoding="utf-8").replace(
        "chapter_1 = 2", "chapter = 2\nchapter_1 = 2"
    )
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert "group_rollup_overlap" in error_codes(exc.value)


def test_inventory_path_traversal_is_rejected(tmp_path: Path):
    manifest = write_fixture(tmp_path)
    text = manifest.read_text(encoding="utf-8").replace(
        'inventory_file = "fixture.csv"', 'inventory_file = "../fixture.csv"'
    )
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert "inventory_path_error" in error_codes(exc.value)


def test_malformed_toml_is_rejected(tmp_path: Path):
    manifest = tmp_path / "bad.toml"
    manifest.write_text("[broken\n", encoding="utf-8")
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)
    assert "manifest_parse_error" in error_codes(exc.value)


def test_committed_collection_validates_when_repository_files_are_present():
    repo_root = Path(__file__).resolve().parents[1]
    manifest = repo_root / "collections/base-game-2026-06-16.toml"
    if not manifest.exists():
        pytest.skip("connector-backed local mirror does not include committed collection files")
    result = validate_collection(manifest)
    assert result.collection_id == "base-game-2026-06-16"
    assert result.puzzle_count == 166
