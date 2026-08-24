from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.errors import ReleaseValidationError
from opus_corpus.release import (
    ConfigRelease,
    ReleaseManifest,
    compute_logical_release_hash,
    derive_release_coverage,
    derive_release_metadata,
    validate_referential_integrity,
    validate_release,
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
        format_version=2,
        corpus_schema_version="0.1",
        collection_id="base-game-2026-06-16",
        collection_inventory_sha256="a" * 64,
        split="base_game_2026_06_16",
        build_software_revision=None,
        build_config_sha256="b" * 64,
        payload_policy="metadata-only",
        coverage_policy="complete",
        release_metadata={"coverage": {"puzzle_count": 1}},
        release_metadata_sha256="c" * 64,
        configs=configs,
        logical_release_sha256="",
    )
    return manifest.with_logical_hash()


def collection(*puzzle_ids: str) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture-collection",
        inventory_sha256="a" * 64,
        puzzle_count=len(puzzle_ids),
        manifest_path=Path("fixture.toml"),
        inventory_path=Path("fixture.csv"),
        inventory_rows=tuple({"puzzle_id": puzzle_id} for puzzle_id in puzzle_ids),
        manifest={},
    )


def records(
    *,
    puzzle_ids: tuple[str, ...] = ("om.puzzle.0001",),
    solutions: list[dict] | None = None,
) -> dict[str, list[dict]]:
    return {
        "puzzles": [{"puzzle_id": puzzle_id} for puzzle_id in puzzle_ids],
        "solutions": solutions
        if solutions is not None
        else [
            {"solution_id": "s1", "puzzle_id": puzzle_ids[0], "verified": True},
            {"solution_id": "s2", "puzzle_id": puzzle_ids[0], "verified": False},
        ],
        "observations": [],
        "normalized": [],
    }


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


def test_logical_release_hash_changes_with_coverage_policy():
    original = sample_manifest()
    changed = ReleaseManifest.from_dict(original.to_dict())
    changed = ReleaseManifest.from_dict({**changed.to_dict(), "coverage_policy": "subset"})
    assert compute_logical_release_hash(changed) != original.logical_release_sha256


@pytest.mark.parametrize("format_version", [1, 999])
def test_validate_release_rejects_unsupported_manifest_versions_before_other_validation(
    monkeypatch: pytest.MonkeyPatch, format_version: int
):
    unsupported = ReleaseManifest.from_dict(
        {
            **sample_manifest().to_dict(),
            "format_version": format_version,
            "logical_release_sha256": "",
        }
    ).with_logical_hash()
    monkeypatch.setattr("opus_corpus.release._read_manifest", lambda *_: unsupported)

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(collection("om.puzzle.0001"), Path("unused"), object())

    assert {error.code for error in exc.value.errors} == {
        "release_manifest_format_unsupported"
    }
    assert str(format_version) in exc.value.errors[0].detail


def test_referential_integrity_rejects_dangling_solution_puzzle():
    value = {
        "puzzles": [{"puzzle_id": "om.puzzle.0001"}],
        "solutions": [{"solution_id": "s1", "puzzle_id": "om.puzzle.9999"}],
        "observations": [],
        "normalized": [],
    }
    with pytest.raises(ReleaseValidationError) as exc:
        validate_referential_integrity(value)
    assert "referential_integrity" in {error.code for error in exc.value.errors}


def test_referential_integrity_rejects_dangling_normalized_solution():
    value = {
        "puzzles": [{"puzzle_id": "om.puzzle.0001"}],
        "solutions": [{"solution_id": "s1", "puzzle_id": "om.puzzle.0001"}],
        "observations": [],
        "normalized": [{"solution_id": "missing", "puzzle_id": "om.puzzle.0001"}],
    }
    with pytest.raises(ReleaseValidationError) as exc:
        validate_referential_integrity(value)
    assert "referential_integrity" in {error.code for error in exc.value.errors}


def test_release_coverage_is_derived_from_canonical_rows():
    coverage = derive_release_coverage(
        collection("om.puzzle.0001"),
        records(),
        coverage_policy="complete",
    )
    assert coverage == {
        "puzzle_count": 1,
        "candidate_solution_count": 2,
        "verified_solution_count": 1,
        "rejected_solution_count": 1,
        "by_puzzle": {
            "om.puzzle.0001": {
                "candidate_solution_count": 2,
                "verified_solution_count": 1,
                "rejected_solution_count": 1,
                "state": "verified",
            }
        },
    }


def test_complete_release_requires_exact_collection_puzzle_set():
    with pytest.raises(ReleaseValidationError) as exc:
        derive_release_coverage(
            collection("om.puzzle.0001", "om.puzzle.0002"),
            records(),
            coverage_policy="complete",
        )
    assert "collection_coverage_mismatch" in {error.code for error in exc.value.errors}


def test_complete_release_requires_verified_solution_for_every_puzzle():
    value = records(
        puzzle_ids=("om.puzzle.0001", "om.puzzle.0002"),
        solutions=[
            {"solution_id": "s1", "puzzle_id": "om.puzzle.0001", "verified": True},
            {"solution_id": "s2", "puzzle_id": "om.puzzle.0002", "verified": False},
        ],
    )
    with pytest.raises(ReleaseValidationError) as exc:
        derive_release_coverage(
            collection("om.puzzle.0001", "om.puzzle.0002"),
            value,
            coverage_policy="complete",
        )
    assert "collection_verified_coverage_incomplete" in {
        error.code for error in exc.value.errors
    }


def test_subset_release_may_cover_collection_subset_and_reports_all_puzzles():
    coverage = derive_release_coverage(
        collection("om.puzzle.0001", "om.puzzle.0002"),
        records(),
        coverage_policy="subset",
    )
    assert coverage["puzzle_count"] == 1
    assert coverage["by_puzzle"]["om.puzzle.0002"] == {
        "candidate_solution_count": 0,
        "verified_solution_count": 0,
        "rejected_solution_count": 0,
        "state": "uncovered",
    }


@pytest.mark.parametrize(
    ("config_name", "identity_field", "rows_with_duplicate"),
    [
        ("puzzles", "puzzle_id", [{"puzzle_id": "om.puzzle.0001"}] * 2),
        (
            "solutions",
            "solution_id",
            [
                {"solution_id": "s1", "puzzle_id": "om.puzzle.0001", "verified": True},
                {"solution_id": "s1", "puzzle_id": "om.puzzle.0001", "verified": False},
            ],
        ),
        (
            "observations",
            "observation_id",
            [{"observation_id": "o1"}, {"observation_id": "o1"}],
        ),
        (
            "normalized",
            "normalized_solution_id",
            [
                {"normalized_solution_id": "n1"},
                {"normalized_solution_id": "n1"},
            ],
        ),
    ],
)
def test_release_coverage_rejects_duplicate_canonical_ids(
    config_name: str, identity_field: str, rows_with_duplicate: list[dict]
):
    value = records(solutions=[])
    value[config_name] = rows_with_duplicate
    with pytest.raises(ReleaseValidationError) as exc:
        derive_release_coverage(
            collection("om.puzzle.0001"),
            value,
            coverage_policy="subset",
        )
    errors = [error for error in exc.value.errors if error.code == "duplicate_canonical_id"]
    assert errors
    assert identity_field in errors[0].detail


def test_release_metadata_rejects_hand_maintained_coverage_counts():
    with pytest.raises(ReleaseValidationError) as exc:
        derive_release_metadata(
            collection("om.puzzle.0001"),
            records(),
            {
                "release_kind": "release",
                "corpus_schema_version": "0.1",
                "coverage": {"puzzle_count": 99, "summary": "human prose is allowed"},
            },
            coverage_policy="complete",
        )
    assert "release_metadata_derived_field" in {error.code for error in exc.value.errors}


def test_release_metadata_release_kind_cannot_relax_complete_coverage():
    with pytest.raises(ReleaseValidationError) as exc:
        derive_release_metadata(
            collection("om.puzzle.0001", "om.puzzle.0002"),
            records(),
            {
                "release_kind": "fixture",
                "corpus_schema_version": "0.1",
                "coverage": {"summary": "descriptive metadata only"},
            },
            coverage_policy="complete",
        )
    assert "collection_coverage_mismatch" in {error.code for error in exc.value.errors}


def test_release_metadata_preserves_coverage_summary_and_adds_derived_counts():
    metadata = derive_release_metadata(
        collection("om.puzzle.0001"),
        records(),
        {
            "release_kind": "release",
            "corpus_schema_version": "0.1",
            "coverage": {"summary": "human prose is allowed"},
        },
        coverage_policy="complete",
    )
    assert metadata["coverage"] == {
        "summary": "human prose is allowed",
        "puzzle_count": 1,
        "candidate_solution_count": 2,
        "verified_solution_count": 1,
        "rejected_solution_count": 1,
        "by_puzzle": {
            "om.puzzle.0001": {
                "candidate_solution_count": 2,
                "verified_solution_count": 1,
                "rejected_solution_count": 1,
                "state": "verified",
            }
        },
    }
