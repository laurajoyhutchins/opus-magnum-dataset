from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

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
        ("puzzles", "puzzle.schema.json", "puzzle_id", ("puzzle_id",), "puzzle_bytes"),
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


def test_unknown_release_config_fails_explicitly():
    from opus_corpus.release_configs import get_release_config

    with pytest.raises(ValueError, match="unknown config 'missing'"):
        get_release_config("missing")

    with pytest.raises(ValueError, match="unknown config 'missing'"):
        validate_payload_policy("missing", [], "metadata-only")
