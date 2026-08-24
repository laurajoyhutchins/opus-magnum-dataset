from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from opus_corpus.cache import CacheIntegrityError, ContentAddressedCache
from opus_corpus.errors import ReleaseValidationError
from opus_corpus.release import validate_referential_integrity
from opus_corpus.schema_resources import load_schema_resource
from opus_corpus.solution_materialization import materialize_solution_facts

ARCHIVE_REVISION = "44006a0eeb0051337640443d1b0576ea24c983f6"
LEADERBOARD_REVISION = "0cfd371ef66cf94eac3f7a7a06bc9ab959495576"


@dataclass(frozen=True)
class FixtureCollection:
    inventory_rows: tuple[dict[str, str], ...]


@pytest.fixture
def collection() -> FixtureCollection:
    return FixtureCollection(
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0001",
                "group": "chapter-1",
                "leaderboard_key": "STABILIZED_WATER",
            },
        )
    )


def _put_fact(
    root: Path,
    *,
    source_id: str,
    revision: str,
    upstream_path: str,
    payload: bytes,
):
    return ContentAddressedCache(root).put_bytes(
        source_id,
        revision,
        upstream_path,
        payload,
        rights_status="local_fetch_only",
    )


def _metadata(data_path: str) -> bytes:
    return (
        "{"
        '"puzzle":"STABILIZED_WATER",'
        '"score":{"cost":7,"instructions":10,"cycles":27,"area":16},'
        f'"dataPath":"{data_path}"'
        "}"
    ).encode()


def _metadata_only_observation(tmp_path: Path, collection: FixtureCollection):
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/orphan.json",
        payload=_metadata("CHAPTER_1/STABILIZED_WATER/missing.solution"),
    )
    result = materialize_solution_facts(collection, tmp_path)
    assert result.artifacts == ()
    assert len(result.observations) == 1
    return result.observations[0]


def test_authoritative_schema_accepts_metadata_only_materialization(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    observation = _metadata_only_observation(tmp_path, collection)
    schema = load_schema_resource("observation.schema.json").schema

    Draft202012Validator(schema).validate(asdict(observation))


def test_authoritative_schema_rejects_null_artifact_for_artifact_role(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    observation = asdict(_metadata_only_observation(tmp_path, collection))
    observation["source_role"] = "artifact"
    schema = load_schema_resource("observation.schema.json").schema

    errors = list(Draft202012Validator(schema).iter_errors(observation))

    assert any(list(error.path) == ["artifact_id"] for error in errors)


def test_release_integrity_accepts_metadata_only_observation(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    observation = asdict(_metadata_only_observation(tmp_path, collection))

    validate_referential_integrity(
        {
            "puzzles": [],
            "solutions": [],
            "observations": [observation],
            "normalized": [],
        }
    )


def test_release_integrity_still_rejects_null_artifact_observation(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    observation = asdict(_metadata_only_observation(tmp_path, collection))
    observation["source_role"] = "artifact"

    with pytest.raises(ReleaseValidationError, match="unknown solution"):
        validate_referential_integrity(
            {
                "puzzles": [],
                "solutions": [],
                "observations": [observation],
                "normalized": [],
            }
        )


def test_cache_receipt_iteration_rejects_forged_upstream_path(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    cache = ContentAddressedCache(tmp_path)
    receipt = _put_fact(
        tmp_path,
        source_id="om-archive",
        revision=ARCHIVE_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/original.solution",
        payload=b"solution",
    )
    receipt_path = cache.receipt_path(
        receipt.source_id,
        receipt.revision,
        receipt.upstream_path,
    )
    raw = receipt_path.read_text(encoding="utf-8").replace(
        "original.solution",
        "forged.solution",
    )
    receipt_path.write_text(raw, encoding="utf-8")

    iterator = getattr(cache, "iter_receipts", None)
    assert iterator is not None, "cache must expose public receipt iteration"
    with pytest.raises(CacheIntegrityError, match="receipt.*identity|path.*mismatch"):
        tuple(iterator("om-archive", ARCHIVE_REVISION))

    with pytest.raises(CacheIntegrityError, match="receipt.*identity|path.*mismatch"):
        materialize_solution_facts(collection, tmp_path)
