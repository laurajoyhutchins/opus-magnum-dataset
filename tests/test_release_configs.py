from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from opus_corpus import config, parquet, payload, release, release_inputs
from opus_corpus.payload import validate_payload_policy


def test_release_config_specs_are_the_single_ordered_release_surface():
    from opus_corpus.release_configs import RELEASE_CONFIGS, get_release_config

    assert [
        (
            spec.name,
            spec.schema_resource,
            spec.canonical_id_field,
            spec.sort_key,
            spec.payload_field,
        )
        for spec in RELEASE_CONFIGS
    ] == [
        ("puzzles", "puzzle.schema.json", "puzzle_id", ("puzzle_id",), None),
        (
            "solutions",
            "solution.schema.json",
            "solution_id",
            ("puzzle_id", "solution_id"),
            "solution_bytes",
        ),
        (
            "observations",
            "observation.schema.json",
            "observation_id",
            ("artifact_id", "observation_id"),
            None,
        ),
        (
            "normalized",
            "normalized.schema.json",
            "normalized_solution_id",
            ("puzzle_id", "solution_id"),
            None,
        ),
    ]
    assert get_release_config("solutions") is RELEASE_CONFIGS[1]

    with pytest.raises(FrozenInstanceError):
        RELEASE_CONFIGS[0].name = "changed"


def test_release_consumers_do_not_publish_duplicate_lookup_maps():
    from opus_corpus.release_configs import CONFIG_NAMES, RELEASE_CONFIGS

    assert config.REQUIRED_CONFIGS is CONFIG_NAMES
    assert CONFIG_NAMES == tuple(spec.name for spec in RELEASE_CONFIGS)
    assert not hasattr(release_inputs, "SCHEMA_FILES")
    assert not hasattr(release_inputs, "SORT_KEYS")
    assert not hasattr(release, "CANONICAL_ID_FIELDS")
    assert not hasattr(parquet, "PAYLOAD_FIELDS")
    assert not hasattr(payload, "PAYLOAD_FIELDS")


def test_unknown_release_config_fails_explicitly():
    from opus_corpus.release_configs import get_release_config

    with pytest.raises(ValueError, match="unknown config 'missing'"):
        get_release_config("missing")

    with pytest.raises(ValueError, match="unknown config 'missing'"):
        validate_payload_policy("missing", [], "metadata-only")
