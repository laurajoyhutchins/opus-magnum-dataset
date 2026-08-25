from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class ReleaseConfigSpec:
    name: str
    schema_resource: str
    canonical_id_field: str
    sort_key: tuple[str, ...]
    payload_field: str | None = None


RELEASE_CONFIGS = (
    ReleaseConfigSpec(
        name="puzzles",
        schema_resource="puzzle.schema.json",
        canonical_id_field="puzzle_id",
        sort_key=("puzzle_id",),
    ),
    ReleaseConfigSpec(
        name="solutions",
        schema_resource="solution.schema.json",
        canonical_id_field="solution_id",
        sort_key=("puzzle_id", "solution_id"),
        payload_field="solution_bytes",
    ),
    ReleaseConfigSpec(
        name="observations",
        schema_resource="observation.schema.json",
        canonical_id_field="observation_id",
        sort_key=("artifact_id", "observation_id"),
    ),
    ReleaseConfigSpec(
        name="normalized",
        schema_resource="normalized.schema.json",
        canonical_id_field="normalized_solution_id",
        sort_key=("puzzle_id", "solution_id"),
    ),
)

CONFIG_NAMES = tuple(spec.name for spec in RELEASE_CONFIGS)
SCHEMA_FILES = MappingProxyType({spec.name: spec.schema_resource for spec in RELEASE_CONFIGS})
SORT_KEYS = MappingProxyType({spec.name: spec.sort_key for spec in RELEASE_CONFIGS})
CANONICAL_ID_FIELDS = MappingProxyType(
    {spec.name: spec.canonical_id_field for spec in RELEASE_CONFIGS}
)
PAYLOAD_FIELDS = MappingProxyType(
    {spec.name: spec.payload_field for spec in RELEASE_CONFIGS if spec.payload_field is not None}
)


def get_release_config(config_name: str) -> ReleaseConfigSpec:
    for spec in RELEASE_CONFIGS:
        if spec.name == config_name:
            return spec
    raise ValueError(f"unknown config {config_name!r}")
