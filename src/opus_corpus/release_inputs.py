from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import ReleaseValidationError, ValidationError
from .hashing import sha256_file

CONFIG_NAMES = ("puzzles", "solutions", "observations", "normalized")
SCHEMA_FILES = {
    "puzzles": "puzzle.schema.json",
    "solutions": "solution.schema.json",
    "observations": "observation.schema.json",
    "normalized": "normalized.schema.json",
}
SORT_KEYS = {
    "puzzles": ("puzzle_id",),
    "solutions": ("puzzle_id", "solution_id"),
    "observations": ("artifact_id", "observation_id"),
    "normalized": ("puzzle_id", "solution_id"),
}


@dataclass(frozen=True)
class LoadedReleaseInputs:
    records: dict[str, list[dict[str, Any]]]
    sources: dict[str, dict[str, str]]


def load_schema(schemas_dir: Path, config_name: str) -> dict[str, Any]:
    path = Path(schemas_dir) / SCHEMA_FILES[config_name]
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError(
            [ValidationError("schema_invalid", str(exc), path.as_posix())]
        ) from exc
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ReleaseValidationError(
            [ValidationError("schema_invalid", str(exc), path.as_posix())]
        ) from exc
    return schema


def sort_records(config_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        keys = SORT_KEYS[config_name]
    except KeyError as exc:
        raise ValueError(f"unknown config {config_name!r}") from exc
    return sorted(rows, key=lambda row: tuple(str(row.get(key, "")) for key in keys))


def load_release_inputs(input_dir: Path, schemas_dir: Path) -> LoadedReleaseInputs:
    input_dir = Path(input_dir)
    records: dict[str, list[dict[str, Any]]] = {}
    sources: dict[str, dict[str, str]] = {}
    errors: list[ValidationError] = []
    for config_name in CONFIG_NAMES:
        path = input_dir / f"{config_name}.jsonl"
        if not path.is_file():
            errors.append(ValidationError("input_missing", f"missing {path.name}", path.as_posix()))
            continue
        schema = load_schema(schemas_dir, config_name)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        config_rows: list[dict[str, Any]] = []
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                errors.append(ValidationError("json_invalid", str(exc), path.as_posix(), line_number))
                continue
            if not isinstance(row, dict):
                errors.append(
                    ValidationError(
                        "schema_invalid", "row must be a JSON object", path.as_posix(), line_number
                    )
                )
                continue
            row_errors = sorted(
                validator.iter_errors(row), key=lambda error: (list(error.path), error.message)
            )
            for error in row_errors:
                errors.append(
                    ValidationError("schema_invalid", error.message, path.as_posix(), line_number)
                )
            config_rows.append(row)
        if not config_rows:
            errors.append(
                ValidationError("input_empty", f"{path.name} contains no rows", path.as_posix())
            )
        records[config_name] = sort_records(config_name, config_rows)
        sources[config_name] = {"path": path.as_posix(), "sha256": sha256_file(path)}
    if errors:
        raise ReleaseValidationError(errors)
    return LoadedReleaseInputs(records=records, sources=sources)
