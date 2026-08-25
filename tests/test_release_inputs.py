from __future__ import annotations

import json
from pathlib import Path

import pytest

from opus_corpus.errors import PayloadPolicyError, ReleaseValidationError
from opus_corpus.payload import validate_payload_policy
from opus_corpus.release_configs import CONFIG_NAMES
from opus_corpus.release_inputs import load_release_inputs, sort_records


def test_solution_sort_is_canonical():
    rows = [
        {"puzzle_id": "om.puzzle.0002", "solution_id": "s2"},
        {"puzzle_id": "om.puzzle.0001", "solution_id": "s9"},
        {"puzzle_id": "om.puzzle.0001", "solution_id": "s1"},
    ]
    sorted_rows = sort_records("solutions", rows)
    assert [(row["puzzle_id"], row["solution_id"]) for row in sorted_rows] == [
        ("om.puzzle.0001", "s1"),
        ("om.puzzle.0001", "s9"),
        ("om.puzzle.0002", "s2"),
    ]


def test_all_config_sort_keys_are_deterministic():
    puzzle_rows = sort_records("puzzles", [{"puzzle_id": "b"}, {"puzzle_id": "a"}])
    assert [row["puzzle_id"] for row in puzzle_rows] == ["a", "b"]

    observation_rows = sort_records(
        "observations",
        [
            {"artifact_id": "x", "observation_id": "b"},
            {"artifact_id": "x", "observation_id": "a"},
        ],
    )
    assert [row["observation_id"] for row in observation_rows] == ["a", "b"]

    normalized_rows = sort_records(
        "normalized",
        [
            {"puzzle_id": "p", "solution_id": "b"},
            {"puzzle_id": "p", "solution_id": "a"},
        ],
    )
    assert [row["solution_id"] for row in normalized_rows] == ["a", "b"]


def test_metadata_only_rejects_solution_bytes():
    with pytest.raises(PayloadPolicyError) as exc:
        validate_payload_policy(
            "solutions",
            [
                {
                    "solution_id": "s",
                    "rights_status": "redistributable",
                    "solution_bytes": "AA==",
                }
            ],
            "metadata-only",
        )
    assert {error.code for error in exc.value.errors} == {"payload_forbidden"}


def test_puzzles_have_no_release_payload_field():
    validate_payload_policy(
        "puzzles",
        [{"puzzle_id": "p", "puzzle_bytes": "not-a-release-field"}],
        "metadata-only",
    )


def test_include_permitted_allows_redistributable_bytes():
    validate_payload_policy(
        "solutions",
        [
            {
                "solution_id": "s",
                "rights_status": "redistributable",
                "solution_bytes": "AA==",
            }
        ],
        "include-permitted",
    )


@pytest.mark.parametrize("rights_status", ["local_fetch_only", "unknown"])
def test_include_permitted_rejects_restricted_bytes(rights_status: str):
    with pytest.raises(PayloadPolicyError) as exc:
        validate_payload_policy(
            "solutions",
            [{"solution_id": "s", "rights_status": rights_status, "solution_bytes": "AA=="}],
            "include-permitted",
        )
    assert "payload_rights_violation" in {error.code for error in exc.value.errors}


def test_invalid_payload_policy_is_rejected():
    with pytest.raises(PayloadPolicyError) as exc:
        validate_payload_policy("puzzles", [], "anything")
    assert "payload_policy_invalid" in {error.code for error in exc.value.errors}


def test_load_release_inputs_validates_all_four_configs():
    root = Path(__file__).resolve().parents[1]
    loaded = load_release_inputs(root / "fixtures/tiny-corpus")
    assert set(loaded.records) == set(CONFIG_NAMES)
    assert all(loaded.records[name] for name in CONFIG_NAMES)


def test_schema_invalid_row_reports_config_and_line(tmp_path: Path):
    fixture = tmp_path / "input"
    fixture.mkdir()
    root = Path(__file__).resolve().parents[1]
    for name in CONFIG_NAMES:
        source = root / "fixtures/tiny-corpus" / f"{name}.jsonl"
        (fixture / source.name).write_bytes(source.read_bytes())
    (fixture / "puzzles.jsonl").write_text(
        json.dumps({"puzzle_id": "bad"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(ReleaseValidationError) as exc:
        load_release_inputs(fixture)
    assert "schema_invalid" in {error.code for error in exc.value.errors}
