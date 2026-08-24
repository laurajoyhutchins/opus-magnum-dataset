from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import ReleaseValidationError, ValidationError
from .hashing import sha256_file
from .release_configs import (
    CONFIG_NAMES,
    SCHEMA_FILES as SCHEMA_FILES,
    SORT_KEYS as SORT_KEYS,
    get_release_config,
)
from .schema_resources import load_schema_resource

_OBSERVATION_OPTIONAL_NULL_FIELDS = (
    "source_role",
    "associated_artifact_path",
    "source_declared_puzzle_id",
    "source_evidence_sha256",
    "source_evidence_byte_length",
)


@dataclass(frozen=True)
class LoadedReleaseInputs:
    records: dict[str, list[dict[str, Any]]]
    sources: dict[str, dict[str, str]]


def load_schema(config_name: str) -> dict[str, Any]:
    return load_schema_resource(get_release_config(config_name).schema_resource).schema


def sort_records(config_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = get_release_config(config_name).sort_key
    return sorted(rows, key=lambda row: tuple(str(row.get(key, "")) for key in keys))


def _canonicalize_row(config_name: str, row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    if config_name == "observations":
        for field in _OBSERVATION_OPTIONAL_NULL_FIELDS:
            item.setdefault(field, None)
    return item


def load_release_inputs(input_dir: Path) -> LoadedReleaseInputs:
    input_dir = Path(input_dir)
    records: dict[str, list[dict[str, Any]]] = {}
    sources: dict[str, dict[str, str]] = {}
    errors: list[ValidationError] = []
    for config_name in CONFIG_NAMES:
        path = input_dir / f"{config_name}.jsonl"
        if not path.is_file():
            errors.append(
                ValidationError("input_missing", f"missing {path.name}", path.as_posix())
            )
            continue
        schema = load_schema(config_name)
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
                errors.append(
                    ValidationError("json_invalid", str(exc), path.as_posix(), line_number)
                )
                continue
            if not isinstance(row, dict):
                errors.append(
                    ValidationError(
                        "schema_invalid",
                        "row must be a JSON object",
                        path.as_posix(),
                        line_number,
                    )
                )
                continue
            row_errors = sorted(
                validator.iter_errors(row),
                key=lambda error: (list(error.path), error.message),
            )
            for error in row_errors:
                errors.append(
                    ValidationError(
                        "schema_invalid", error.message, path.as_posix(), line_number
                    )
                )
            config_rows.append(_canonicalize_row(config_name, row))
        if not config_rows:
            errors.append(
                ValidationError("input_empty", f"{path.name} contains no rows", path.as_posix())
            )
        records[config_name] = sort_records(config_name, config_rows)
        sources[config_name] = {
            "path": path.relative_to(input_dir).as_posix(),
            "sha256": sha256_file(path),
        }
    if errors:
        raise ReleaseValidationError(errors)
    return LoadedReleaseInputs(records=records, sources=sources)
