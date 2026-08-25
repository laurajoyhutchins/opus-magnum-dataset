from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .directory_publication import publish_directory
from .errors import CorpusError
from .hashing import canonical_json_bytes
from .release_inputs import load_schema, sort_records

SOLUTION_VIEW_NAMES = (
    "all-verified",
    "vanilla-constructible",
    "record-eligible",
)


class SolutionViewError(CorpusError):
    """Raised when release solution rows cannot produce deterministic views."""


def _validated_solution_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    validator = Draft202012Validator(
        load_schema("solutions"),
        format_checker=FormatChecker(),
    )
    validated: list[dict[str, Any]] = []
    solution_ids: set[str] = set()

    for index, value in enumerate(rows, start=1):
        if not isinstance(value, Mapping):
            raise SolutionViewError(f"solution row {index} must be a mapping")
        row = dict(value)
        errors = sorted(
            validator.iter_errors(row),
            key=lambda error: (list(error.path), error.message),
        )
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise SolutionViewError(
                f"solution row {index} violates the release schema: {detail}"
            )

        solution_id = row["solution_id"]
        if solution_id in solution_ids:
            raise SolutionViewError(f"duplicate solution_id {solution_id!r}")
        solution_ids.add(solution_id)
        validated.append(row)

    return sort_records("solutions", validated)


def derive_solution_views(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Derive deterministic research views from canonical release solution rows."""

    solutions = _validated_solution_rows(rows)
    verified = [row for row in solutions if row["verified"] is True]
    return {
        "all-verified": verified,
        "vanilla-constructible": [
            row for row in verified if row["vanilla_constructible"] is True
        ],
        "record-eligible": [row for row in verified if row["record_eligible"] is True],
    }


def materialize_solution_views(
    rows: Iterable[Mapping[str, Any]],
    destination: Path,
) -> Path:
    """Atomically materialize deterministic JSONL solution-view projections."""

    views = derive_solution_views(rows)
    destination = Path(destination)
    with publish_directory(destination) as candidate:
        for view_name in SOLUTION_VIEW_NAMES:
            payload = b"".join(
                canonical_json_bytes(row) + b"\n" for row in views[view_name]
            )
            (candidate / f"{view_name}.jsonl").write_bytes(payload)
    return destination
