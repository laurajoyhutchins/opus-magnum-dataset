from __future__ import annotations

import pytest

from opus_corpus.errors import ReleaseValidationError
from opus_corpus.release import (
    ConfigRelease,
    ReleaseManifest,
    compute_logical_release_hash,
    validate_referential_integrity,
)


def sample_manifest() -> ReleaseManifest:
    configs = {
        name: ConfigRelease(
            schema_path=f"schemas/{name}.json",
            schema_sha256=name * 8 if len(name) == 8 else (name + "0" * 64)[:64],
            records_sha256=name[0] * 64,
            row_count=1,
            parquet_path=f"data/{name}/split-00000-of-00001.parquet",
            parquet_sha256=name[-1] * 64,
            source_path=f"fixtures/{name}.jsonl",
            source_sha256="f" * 64,
        )
        for name in ("puzzles", "solutions", "observations", "normalized")
    }
    manifest = ReleaseManifest(
        format_version=1,
        corpus_schema_version="0.1",
        collection_id="base-game-2026-06-16",
        collection_inventory_sha256="a" * 64,
        split="base_game_2026_06_16",
        build_software_revision=None,
        build_config_sha256="b" * 64,
        payload_policy="metadata-only",
        release_metadata={"coverage": {"puzzle_count": 1}},
        release_metadata_sha256="c" * 64,
        configs=configs,
        logical_release_sha256="",
    )
    return manifest.with_logical_hash()


def test_release_manifest_round_trips():
    original = sample_manifest()
    restored = ReleaseManifest.from_dict(original.to_dict())
    assert restored == original
    assert restored.logical_release_sha256 == compute_logical_release_hash(restored)


def test_logical_release_hash_ignores_physical_parquet_hashes():
    original = sample_manifest()
    changed = ReleaseManifest.from_dict(original.to_dict())
    first = changed.configs["solutions"]
    changed.configs["solutions"] = ConfigRelease(
        schema_path=first.schema_path,
        schema_sha256=first.schema_sha256,
        records_sha256=first.records_sha256,
        row_count=first.row_count,
        parquet_path=first.parquet_path,
        parquet_sha256="0" * 64,
        source_path=first.source_path,
        source_sha256=first.source_sha256,
    )
    assert compute_logical_release_hash(changed) == original.logical_release_sha256


def test_logical_release_hash_changes_with_record_hash():
    original = sample_manifest()
    changed = ReleaseManifest.from_dict(original.to_dict())
    first = changed.configs["solutions"]
    changed.configs["solutions"] = ConfigRelease(
        schema_path=first.schema_path,
        schema_sha256=first.schema_sha256,
        records_sha256="0" * 64,
        row_count=first.row_count,
        parquet_path=first.parquet_path,
        parquet_sha256=first.parquet_sha256,
        source_path=first.source_path,
        source_sha256=first.source_sha256,
    )
    assert compute_logical_release_hash(changed) != original.logical_release_sha256


def test_referential_integrity_rejects_dangling_solution_puzzle():
    records = {
        "puzzles": [{"puzzle_id": "om.puzzle.0001"}],
        "solutions": [{"solution_id": "s1", "puzzle_id": "om.puzzle.9999"}],
        "observations": [],
        "normalized": [],
    }
    with pytest.raises(ReleaseValidationError) as exc:
        validate_referential_integrity(records)
    assert "referential_integrity" in {error.code for error in exc.value.errors}


def test_referential_integrity_rejects_dangling_normalized_solution():
    records = {
        "puzzles": [{"puzzle_id": "om.puzzle.0001"}],
        "solutions": [{"solution_id": "s1", "puzzle_id": "om.puzzle.0001"}],
        "observations": [],
        "normalized": [{"solution_id": "missing", "puzzle_id": "om.puzzle.0001"}],
    }
    with pytest.raises(ReleaseValidationError) as exc:
        validate_referential_integrity(records)
    assert "referential_integrity" in {error.code for error in exc.value.errors}
