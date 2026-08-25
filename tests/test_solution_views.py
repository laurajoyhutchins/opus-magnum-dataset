from __future__ import annotations

import json
from pathlib import Path

import pytest

from opus_corpus.solution_views import (
    SolutionViewError,
    derive_solution_views,
    materialize_solution_views,
)


def _solution(
    solution_id: str,
    *,
    puzzle_id: str = "om.puzzle.0001",
    verified: bool = True,
    vanilla_constructible: bool | None = True,
    record_eligible: bool | None = True,
) -> dict[str, object]:
    return {
        "solution_id": solution_id,
        "solution_sha256": "a" * 64,
        "puzzle_id": puzzle_id,
        "puzzle_artifact_id": "om.puzzle-artifact.sha256." + "b" * 64,
        "solution_format": "solution",
        "solution_bytes": None,
        "rights_status": "local_fetch_only",
        "verified": verified,
        "validation_profile": "default-v1",
        "verifier_revision": "rev-1",
        "cost": 10 if verified else None,
        "cycles": 20 if verified else None,
        "area": 30 if verified else None,
        "instructions": 40 if verified else None,
        "vanilla_constructible": vanilla_constructible,
        "record_eligible": record_eligible,
        "normalized_solution_id": "om.normalized.solution.test" if verified else None,
        "source_count": 1,
        "collection_id": "base-game-2026-06-16",
    }


def test_derive_solution_views_selects_only_declared_verified_predicates() -> None:
    unverified = _solution(
        "om.solution.sha256.0",
        verified=False,
        vanilla_constructible=True,
        record_eligible=True,
    )
    verified_not_special = _solution(
        "om.solution.sha256.2",
        vanilla_constructible=False,
        record_eligible=False,
    )
    vanilla_only = _solution(
        "om.solution.sha256.1",
        vanilla_constructible=True,
        record_eligible=False,
    )
    record_only = _solution(
        "om.solution.sha256.3",
        vanilla_constructible=False,
        record_eligible=True,
    )

    views = derive_solution_views(
        [record_only, verified_not_special, unverified, vanilla_only]
    )

    assert [row["solution_id"] for row in views["all-verified"]] == [
        "om.solution.sha256.1",
        "om.solution.sha256.2",
        "om.solution.sha256.3",
    ]
    assert views["vanilla-constructible"] == [vanilla_only]
    assert views["record-eligible"] == [record_only]


def test_derive_solution_views_rejects_malformed_release_rows() -> None:
    malformed = _solution("om.solution.sha256.bad")
    del malformed["vanilla_constructible"]

    with pytest.raises(SolutionViewError, match="solution row 1 violates the release schema"):
        derive_solution_views([malformed])


def test_derive_solution_views_rejects_duplicate_solution_identity() -> None:
    duplicate = _solution("om.solution.sha256.same")

    with pytest.raises(SolutionViewError, match="duplicate solution_id"):
        derive_solution_views([duplicate, dict(duplicate)])


def test_derive_solution_views_returns_independent_rows_per_view() -> None:
    row = _solution("om.solution.sha256.shared")

    views = derive_solution_views([row])
    views["vanilla-constructible"][0]["cost"] = 999

    assert views["all-verified"][0]["cost"] == 10
    assert views["record-eligible"][0]["cost"] == 10
    assert row["cost"] == 10


def test_materialize_solution_views_is_order_independent_and_byte_deterministic(
    tmp_path: Path,
) -> None:
    first = _solution(
        "om.solution.sha256.2",
        puzzle_id="om.puzzle.0002",
        vanilla_constructible=False,
        record_eligible=True,
    )
    second = _solution(
        "om.solution.sha256.1",
        puzzle_id="om.puzzle.0001",
        vanilla_constructible=True,
        record_eligible=False,
    )

    left = tmp_path / "left"
    right = tmp_path / "right"
    materialize_solution_views([first, second], left)
    materialize_solution_views([second, first], right)

    assert sorted(path.name for path in left.iterdir()) == [
        "all-verified.jsonl",
        "record-eligible.jsonl",
        "vanilla-constructible.jsonl",
    ]
    for name in (
        "all-verified.jsonl",
        "vanilla-constructible.jsonl",
        "record-eligible.jsonl",
    ):
        assert (left / name).read_bytes() == (right / name).read_bytes()

    all_verified = [
        json.loads(line)
        for line in (left / "all-verified.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all_verified == [second, first]
