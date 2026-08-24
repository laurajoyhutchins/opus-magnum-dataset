from __future__ import annotations

import csv
import datetime as dt
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .errors import CollectionValidationError, ValidationError
from .hashing import sha256_file

INVENTORY_HEADER = [
    "puzzle_id",
    "display_name",
    "kind",
    "group",
    "game_puzzle_id",
    "leaderboard_key",
    "puzzle_type",
]


@dataclass(frozen=True)
class CollectionDefinition:
    collection_id: str
    inventory_sha256: str
    puzzle_count: int
    manifest_path: Path
    inventory_path: Path
    inventory_rows: tuple[dict[str, str], ...]
    manifest: dict[str, Any]


def _schemas_root() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    path = _schemas_root() / name
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _jsonable(value: Any) -> Any:
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _schema_errors(
    validator: Draft202012Validator,
    value: Any,
    *,
    code: str,
    path: str,
    row: int | None = None,
) -> list[ValidationError]:
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: (list(error.path), error.message),
    )
    return [ValidationError(code, error.message, path, row) for error in errors]


def validate_collection(manifest_path: Path) -> CollectionDefinition:
    manifest_path = Path(manifest_path).resolve()
    errors: list[ValidationError] = []
    rel_manifest = manifest_path.as_posix()
    try:
        with manifest_path.open("rb") as handle:
            raw_manifest = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CollectionValidationError(
            [ValidationError("manifest_parse_error", str(exc), rel_manifest)]
        ) from exc

    manifest = _jsonable(raw_manifest)
    manifest_validator = Draft202012Validator(_load_schema("collection-manifest.schema.json"))
    errors.extend(
        _schema_errors(
            manifest_validator,
            manifest,
            code="manifest_schema_error",
            path=rel_manifest,
        )
    )

    inventory_name = manifest.get("inventory_file")
    inventory_path: Path | None = None
    if not isinstance(inventory_name, str) or Path(inventory_name).name != inventory_name:
        errors.append(
            ValidationError(
                "inventory_path_error",
                "inventory_file must be a basename in the manifest directory",
                rel_manifest,
            )
        )
    else:
        inventory_path = manifest_path.parent / inventory_name

    rows: list[dict[str, str]] = []
    if inventory_path is not None:
        if not inventory_path.is_file():
            errors.append(
                ValidationError(
                    "inventory_missing",
                    f"inventory not found: {inventory_name}",
                    rel_manifest,
                )
            )
        else:
            expected_hash = manifest.get("inventory_sha256")
            actual_hash = sha256_file(inventory_path)
            if isinstance(expected_hash, str) and actual_hash != expected_hash:
                errors.append(
                    ValidationError(
                        "inventory_hash_mismatch",
                        f"expected {expected_hash}, got {actual_hash}",
                        inventory_path.as_posix(),
                    )
                )
            try:
                text = inventory_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                errors.append(
                    ValidationError("inventory_decode_error", str(exc), inventory_path.as_posix())
                )
            else:
                parsed = list(csv.reader(text.splitlines()))
                if not parsed or parsed[0] != INVENTORY_HEADER:
                    errors.append(
                        ValidationError(
                            "inventory_header_error",
                            f"expected header {','.join(INVENTORY_HEADER)}",
                            inventory_path.as_posix(),
                            1,
                        )
                    )
                else:
                    row_validator = Draft202012Validator(
                        _load_schema("collection-inventory-row.schema.json")
                    )
                    for line_number, values in enumerate(parsed[1:], start=2):
                        if len(values) != len(INVENTORY_HEADER):
                            errors.append(
                                ValidationError(
                                    "inventory_row_error",
                                    f"expected {len(INVENTORY_HEADER)} columns, got {len(values)}",
                                    inventory_path.as_posix(),
                                    line_number,
                                )
                            )
                            continue
                        row = dict(zip(INVENTORY_HEADER, values, strict=True))
                        errors.extend(
                            _schema_errors(
                                row_validator,
                                row,
                                code="inventory_row_error",
                                path=inventory_path.as_posix(),
                                row=line_number,
                            )
                        )
                        rows.append(row)

    if rows:
        for field, code in (
            ("puzzle_id", "duplicate_puzzle_id"),
            ("game_puzzle_id", "duplicate_game_puzzle_id"),
            ("leaderboard_key", "duplicate_leaderboard_key"),
        ):
            seen: dict[str, int] = {}
            for index, row in enumerate(rows, start=2):
                value = row[field]
                if value in seen:
                    errors.append(
                        ValidationError(
                            code,
                            f"duplicate {field} {value!r}; first seen on row {seen[value]}",
                            inventory_path.as_posix() if inventory_path else rel_manifest,
                            index,
                        )
                    )
                else:
                    seen[value] = index

        for offset, row in enumerate(rows, start=1):
            expected = f"om.puzzle.{offset:04d}"
            if row["puzzle_id"] != expected:
                errors.append(
                    ValidationError(
                        "puzzle_id_sequence_error",
                        f"expected {expected}, got {row['puzzle_id']}",
                        inventory_path.as_posix() if inventory_path else rel_manifest,
                        offset + 1,
                    )
                )

        declared_count = manifest.get("puzzle_count")
        if isinstance(declared_count, int) and declared_count != len(rows):
            errors.append(
                ValidationError(
                    "puzzle_count_mismatch",
                    f"manifest declares {declared_count}, inventory contains {len(rows)}",
                    rel_manifest,
                )
            )

        group_counts = manifest.get("group_counts")
        if isinstance(group_counts, dict):
            observed = {key: 0 for key in group_counts}
            for index, row in enumerate(rows, start=2):
                matches: list[str] = []
                for key in group_counts:
                    prefix = key.replace("_", "-")
                    if row["group"] == prefix or row["group"].startswith(prefix + "-"):
                        matches.append(key)
                if not matches:
                    errors.append(
                        ValidationError(
                            "group_rollup_unmatched",
                            f"group {row['group']!r} matches no group_counts rollup",
                            inventory_path.as_posix() if inventory_path else rel_manifest,
                            index,
                        )
                    )
                elif len(matches) > 1:
                    errors.append(
                        ValidationError(
                            "group_rollup_overlap",
                            f"group {row['group']!r} matches {matches}",
                            inventory_path.as_posix() if inventory_path else rel_manifest,
                            index,
                        )
                    )
                else:
                    observed[matches[0]] += 1
            for key, expected in group_counts.items():
                if isinstance(expected, int) and observed.get(key) != expected:
                    errors.append(
                        ValidationError(
                            "group_counts_mismatch",
                            f"{key} expected {expected}, observed {observed.get(key, 0)}",
                            rel_manifest,
                        )
                    )

    if errors:
        raise CollectionValidationError(errors)

    assert inventory_path is not None
    return CollectionDefinition(
        collection_id=manifest["collection_id"],
        inventory_sha256=manifest["inventory_sha256"],
        puzzle_count=manifest["puzzle_count"],
        manifest_path=manifest_path,
        inventory_path=inventory_path,
        inventory_rows=tuple(rows),
        manifest=manifest,
    )


def validate_all_collections(root: Path) -> list[CollectionDefinition]:
    collection_dir = Path(root) / "collections"
    return [validate_collection(path) for path in sorted(collection_dir.glob("*.toml"))]
