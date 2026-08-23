from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from tools.validate_collections import ValidationError, validate_collection


HEADER = "puzzle_id,display_name,kind,group,game_puzzle_id,leaderboard_key,puzzle_type\n"


class CollectionValidatorTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        rows: list[str] | None = None,
        *,
        puzzle_count: int | None = None,
        group_counts: dict[str, int] | None = None,
        inventory_file: str = "fixture.csv",
        hash_override: str | None = None,
    ) -> Path:
        rows = rows or [
            "om.puzzle.0001,One,campaign,chapter-1,P007,ONE,normal\n",
            "om.puzzle.0002,Two,journal,journal-xcix-i,P008,TWO,normal\n",
        ]
        inventory = root / "fixture.csv"
        raw = (HEADER + "".join(rows)).encode("utf-8")
        inventory.write_bytes(raw)
        digest = hash_override or hashlib.sha256(raw).hexdigest()
        counts = group_counts or {"chapter_1": 1, "journal_xcix": 1}
        count_lines = "\n".join(f"{key} = {value}" for key, value in counts.items())
        manifest = root / "fixture.toml"
        manifest.write_text(
            f'''schema_version = 1
collection_id = "fixture-2026-08-23"
title = "Fixture"
effective_date = "2026-08-23"
status = "frozen"
puzzle_count = {puzzle_count if puzzle_count is not None else len(rows)}
inventory_file = "{inventory_file}"
inventory_sha256 = "{digest}"
scope = "test"
excludes = []

[membership_source]
source = "example/source"
revision = "0123456789abcdef0123456789abcdef01234567"
puzzle_model = "Puzzle.kt"
group_model = "Group.kt"
collection_model = "Collection.kt"

[release_evidence]
journal_final_issue_date = "2026-06-16"
journal_issue_count = 24
source_url = "https://example.invalid/releases"

[group_counts]
{count_lines}
''',
            encoding="utf-8",
        )
        return manifest

    def assert_error(self, errors: list[ValidationError], code: str) -> None:
        self.assertIn(code, [error.code for error in errors], errors)

    def test_committed_base_game_collection_is_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        errors = validate_collection(root / "collections/base-game-2026-06-16.toml")
        self.assertEqual([], errors)

    def test_valid_fixture_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp))
            self.assertEqual([], validate_collection(manifest))

    def test_hash_drift_is_rejected_before_row_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), hash_override="0" * 64)
            errors = validate_collection(manifest)
            self.assert_error(errors, "inventory_hash_mismatch")

    def test_row_count_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), puzzle_count=3)
            self.assert_error(validate_collection(manifest), "puzzle_count_mismatch")

    def test_duplicate_identifiers_are_rejected(self) -> None:
        rows = [
            "om.puzzle.0001,One,campaign,chapter-1,P007,ONE,normal\n",
            "om.puzzle.0001,Two,journal,journal-xcix-i,P007,ONE,normal\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), rows)
            errors = validate_collection(manifest)
            self.assert_error(errors, "duplicate_puzzle_id")
            self.assert_error(errors, "duplicate_game_puzzle_id")
            self.assert_error(errors, "duplicate_leaderboard_key")

    def test_puzzle_ids_must_be_ordered_and_contiguous(self) -> None:
        rows = [
            "om.puzzle.0002,Two,campaign,chapter-1,P007,TWO,normal\n",
            "om.puzzle.0001,One,journal,journal-xcix-i,P008,ONE,normal\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), rows)
            self.assert_error(validate_collection(manifest), "puzzle_id_sequence_error")

    def test_malformed_inventory_fields_are_rejected(self) -> None:
        rows = [
            "om.puzzle.0001,One,campaign,Chapter One,p7,bad-key,banana\n",
            "om.puzzle.0002,Two,journal,journal-xcix-i,P008,TWO,normal\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), rows)
            self.assert_error(validate_collection(manifest), "inventory_row_error")

    def test_exact_csv_header_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._write_fixture(root)
            inventory = root / "fixture.csv"
            bad = inventory.read_text(encoding="utf-8").replace("puzzle_id,display_name", "display_name,puzzle_id", 1)
            inventory.write_text(bad, encoding="utf-8")
            digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
            text = manifest.read_text(encoding="utf-8")
            text = text.replace(hashlib.sha256((HEADER + "om.puzzle.0001,One,campaign,chapter-1,P007,ONE,normal\nom.puzzle.0002,Two,journal,journal-xcix-i,P008,TWO,normal\n").encode()).hexdigest(), digest)
            manifest.write_text(text, encoding="utf-8")
            self.assert_error(validate_collection(manifest), "inventory_header_error")

    def test_group_rollups_match_finer_issue_groups(self) -> None:
        rows = [
            "om.puzzle.0001,One,journal,journal-xcix-i,P007,ONE,normal\n",
            "om.puzzle.0002,Two,journal,journal-xcix-xii,P008,TWO,normal\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), rows, group_counts={"journal_xcix": 2})
            self.assertEqual([], validate_collection(manifest))

    def test_unmatched_group_rollup_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), group_counts={"chapter_1": 1, "journal_cviii": 1})
            self.assert_error(validate_collection(manifest), "group_rollup_unmatched")

    def test_overlapping_group_rollups_are_rejected(self) -> None:
        rows = [
            "om.puzzle.0001,One,journal,journal-xcix-i,P007,ONE,normal\n",
            "om.puzzle.0002,Two,journal,journal-xcix-ii,P008,TWO,normal\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(
                Path(tmp), rows, group_counts={"journal": 2, "journal_xcix": 2}
            )
            self.assert_error(validate_collection(manifest), "group_rollup_overlap")

    def test_inventory_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), inventory_file="../fixture.csv")
            self.assert_error(validate_collection(manifest), "inventory_path_error")

    def test_malformed_toml_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text("not = [valid", encoding="utf-8")
            self.assert_error(validate_collection(path), "manifest_parse_error")

    def test_error_order_is_deterministic(self) -> None:
        rows = [
            "om.puzzle.0002,One,campaign,chapter-1,P007,ONE,normal\n",
            "om.puzzle.0002,Two,campaign,chapter-1,P007,ONE,normal\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_fixture(Path(tmp), rows, group_counts={"chapter_1": 99})
            first = validate_collection(manifest)
            second = validate_collection(manifest)
            self.assertEqual(first, second)
            self.assertEqual(first, sorted(first, key=lambda e: (str(e.path), e.row or 0, e.code, e.detail)))


if __name__ == "__main__":
    unittest.main()
