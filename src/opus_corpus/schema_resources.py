from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .errors import ConfigurationError
from .hashing import sha256_bytes


@dataclass(frozen=True)
class SchemaResource:
    name: str
    logical_path: str
    schema: dict[str, Any]
    sha256: str


def load_schema_resource(name: str) -> SchemaResource:
    if Path(name).name != name:
        raise ConfigurationError(f"invalid schema resource name: {name!r}")

    resource = files("opus_corpus").joinpath("schemas").joinpath(name)
    try:
        raw = resource.read_bytes()
    except OSError as exc:
        raise ConfigurationError(f"schema resource not found: {name}") from exc

    try:
        schema = json.loads(raw)
        Draft202012Validator.check_schema(schema)
    except (UnicodeDecodeError, json.JSONDecodeError, Exception) as exc:
        raise ConfigurationError(f"invalid schema resource {name}: {exc}") from exc

    if not isinstance(schema, dict):
        raise ConfigurationError(f"invalid schema resource {name}: schema must be an object")

    return SchemaResource(
        name=name,
        logical_path=f"schemas/{name}",
        schema=schema,
        sha256=sha256_bytes(raw),
    )
