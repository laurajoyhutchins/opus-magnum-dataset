from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import opus_corpus.solution_materialization as solution_materialization
from opus_corpus.adapters.om_archive import OmArchiveAdapter
from opus_corpus.adapters.om_leaderboard import OmLeaderboardAdapter
from opus_corpus.cache import CacheReceipt, ContentAddressedCache
from opus_corpus.content_store import ContentStore, ContentStoreError
from opus_corpus.schema_resources import load_schema_resource
from opus_corpus.solution_materialization import (
    SolutionMaterializationError,
    materialize_solution_facts,
)

ARCHIVE_REVISION = "44006a0eeb0051337640443d1b0576ea24c983f6"
LEADERBOARD_REVISION = "0cfd371ef66cf94eac3f7a7a06bc9ab959495576"
RETRIEVED_AT = "2026-08-24T12:00:00+00:00"


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
            {
                "puzzle_id": "om.puzzle.0092",
                "group": "journal-xcix-x",
                "leaderboard_key": "TOUCHSTONE",
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
    rights_status: str = "local_fetch_only",
) -> CacheReceipt:
    store = ContentStore(root)
    stored = store.put_bytes(payload)
    receipt = CacheReceipt(
        source_id=source_id,
        revision=revision,
        upstream_path=upstream_path,
        sha256=stored.sha256,
        byte_length=stored.byte_length,
        rights_status=rights_status,
        retrieved_at=RETRIEVED_AT,
    )
    cache = ContentAddressedCache(root)
    path = cache.receipt_path(source_id, revision, upstream_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return receipt


def _leaderboard_metadata(
    data_path: str,
    *,
    cost: int = 100,
    puzzle: str = "STABILIZED_WATER",
) -> bytes:
    return json.dumps(
        {
            "puzzle": puzzle,
            "score": {
                "cost": cost,
                "instructions": 10,
                "cycles": 27,
                "area": 16,
            },
            "displayLink": "https://files.example/solution.gif",
            "dataLink": "https://zlbb.example/solution",
            "dataPath": data_path,
        },
        sort_keys=True,
    ).encode()


def _observation_validator() -> Draft202012Validator:
    schema = load_schema_resource("observation.schema.json").schema
    return Draft202012Validator(schema)


def test_identical_cross_source_solution_bytes_deduplicate_but_keep_observations(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    payload = b"same-solution-bytes"
    archive_path = "CHAPTER_1/STABILIZED_WATER/archive.solution"
    leaderboard_path = "CHAPTER_1/STABILIZED_WATER/current.solution"
    metadata_path = "CHAPTER_1/STABILIZED_WATER/current.json"
    _put_fact(
        tmp_path,
        source_id="om-archive",
        revision=ARCHIVE_REVISION,
        upstream_path=archive_path,
        payload=payload,
    )
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path=leaderboard_path,
        payload=payload,
    )
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path=metadata_path,
        payload=_leaderboard_metadata(leaderboard_path, cost=99),
    )

    result = materialize_solution_facts(collection, tmp_path)

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_kind == "solution"
    assert artifact.artifact_format == "solution"
    assert artifact.puzzle_id == "om.puzzle.0001"
    artifact_observations = [
        row for row in result.observations if row.artifact_id == artifact.artifact_id
    ]
    assert {(row.source_id, row.source_role) for row in artifact_observations} == {
        ("om-archive", "artifact"),
        ("om-leaderboard", "artifact"),
        ("om-leaderboard", "metadata"),
    }
    metadata = next(row for row in artifact_observations if row.source_role == "metadata")
    assert metadata.claimed_cost == 99
    assert metadata.claimed_cycles == 27
    assert metadata.claimed_area == 16
    assert metadata.claimed_instructions == 10
    assert metadata.observed_sha256 == artifact.sha256
    assert metadata.source_evidence_sha256 != artifact.sha256
    assert metadata.source_object_id is None
    assert metadata.associated_artifact_path == leaderboard_path
    assert metadata.source_declared_puzzle_id == "STABILIZED_WATER"
    assert metadata.source_url == "https://zlbb.example/solution"


def test_unpaired_leaderboard_metadata_is_preserved_as_observation(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    metadata_path = "CHAPTER_1/STABILIZED_WATER/orphan.json"
    missing_path = "CHAPTER_1/STABILIZED_WATER/missing.solution"
    metadata_receipt = _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path=metadata_path,
        payload=_leaderboard_metadata(missing_path, cost=7),
    )

    result = materialize_solution_facts(collection, tmp_path)

    assert result.artifacts == ()
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.artifact_id is None
    assert observation.puzzle_id == "om.puzzle.0001"
    assert observation.source_role == "metadata"
    assert observation.source_object_id is None
    assert observation.associated_artifact_path == missing_path
    assert observation.source_declared_puzzle_id == "STABILIZED_WATER"
    assert observation.claimed_cost == 7
    assert observation.observed_sha256 is None
    assert observation.source_evidence_sha256 == metadata_receipt.sha256


def test_relative_data_path_pairs_with_solution_in_same_directory(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    solution_path = "CHAPTER_1/STABILIZED_WATER/current.solution"
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path=solution_path,
        payload=b"solution",
    )
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/current.json",
        payload=_leaderboard_metadata("current.solution"),
    )

    result = materialize_solution_facts(collection, tmp_path)

    assert len(result.artifacts) == 1
    metadata = next(row for row in result.observations if row.source_role == "metadata")
    assert metadata.artifact_id == result.artifacts[0].artifact_id
    assert metadata.associated_artifact_path == solution_path


def test_metadata_data_path_cannot_escape_its_puzzle_directory(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/bad.json",
        payload=_leaderboard_metadata("../OTHER/foreign.solution"),
    )

    with pytest.raises(SolutionMaterializationError, match="dataPath"):
        materialize_solution_facts(collection, tmp_path)


def test_metadata_cannot_claim_solution_from_different_puzzle(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    foreign_path = "JOURNAL_X/TOUCHSTONE/foreign.solution"
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path=foreign_path,
        payload=b"foreign",
    )
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/bad.json",
        payload=_leaderboard_metadata(foreign_path),
    )

    with pytest.raises(SolutionMaterializationError, match="different puzzle"):
        materialize_solution_facts(collection, tmp_path)


def test_metadata_cannot_name_different_puzzle_when_target_is_missing(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    foreign_path = "JOURNAL_X/TOUCHSTONE/missing.solution"
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/bad.json",
        payload=_leaderboard_metadata(foreign_path),
    )

    with pytest.raises(SolutionMaterializationError, match="different puzzle"):
        materialize_solution_facts(collection, tmp_path)


def test_source_declared_puzzle_identifier_is_preserved_when_it_disagrees(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    solution_path = "CHAPTER_1/STABILIZED_WATER/current.solution"
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path=solution_path,
        payload=b"solution",
    )
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/current.json",
        payload=_leaderboard_metadata(solution_path, puzzle="SOURCE_DISAGREES"),
    )

    result = materialize_solution_facts(collection, tmp_path)

    metadata = next(row for row in result.observations if row.source_role == "metadata")
    assert metadata.puzzle_id == "om.puzzle.0001"
    assert metadata.source_declared_puzzle_id == "SOURCE_DISAGREES"


def test_materialized_observations_conform_to_canonical_schema(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    solution_path = "CHAPTER_1/STABILIZED_WATER/current.solution"
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path=solution_path,
        payload=b"solution",
    )
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/current.json",
        payload=_leaderboard_metadata(solution_path),
    )
    _put_fact(
        tmp_path,
        source_id="om-leaderboard",
        revision=LEADERBOARD_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/orphan.json",
        payload=_leaderboard_metadata("CHAPTER_1/STABILIZED_WATER/missing.solution"),
    )

    result = materialize_solution_facts(collection, tmp_path)
    validator = _observation_validator()

    for observation in result.observations:
        validator.validate(asdict(observation))


def test_existing_observation_fixture_remains_schema_valid() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "tiny-corpus" / "observations.jsonl"
    row = json.loads(fixture_path.read_text(encoding="utf-8").strip())
    _observation_validator().validate(row)


def test_materializer_and_adapters_share_source_layout_objects() -> None:
    archive_source = getattr(solution_materialization, "OM_ARCHIVE_SOURCE", None)
    leaderboard_source = getattr(solution_materialization, "OM_LEADERBOARD_SOURCE", None)

    assert archive_source is not None
    assert leaderboard_source is not None
    assert getattr(OmArchiveAdapter, "source_layout", None) is archive_source
    assert getattr(OmLeaderboardAdapter, "source_layout", None) is leaderboard_source


def test_corrupt_solution_object_fails_closed(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    receipt = _put_fact(
        tmp_path,
        source_id="om-archive",
        revision=ARCHIVE_REVISION,
        upstream_path="CHAPTER_1/STABILIZED_WATER/archive.solution",
        payload=b"valid",
    )
    ContentAddressedCache(tmp_path).object_path(receipt.sha256).write_bytes(b"corrupt")

    with pytest.raises(ContentStoreError, match="content object|corrupt"):
        materialize_solution_facts(collection, tmp_path)


def test_output_is_independent_of_cache_root_and_fact_insertion_order(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    facts = [
        (
            "om-archive",
            ARCHIVE_REVISION,
            "CHAPTER_1/STABILIZED_WATER/a.solution",
            b"same",
        ),
        (
            "om-leaderboard",
            LEADERBOARD_REVISION,
            "CHAPTER_1/STABILIZED_WATER/b.solution",
            b"same",
        ),
        (
            "om-leaderboard",
            LEADERBOARD_REVISION,
            "CHAPTER_1/STABILIZED_WATER/b.json",
            _leaderboard_metadata("b.solution"),
        ),
    ]
    left = tmp_path / "left"
    right = tmp_path / "right"
    for source_id, revision, path, payload in facts:
        _put_fact(
            left, source_id=source_id, revision=revision, upstream_path=path, payload=payload
        )
    for source_id, revision, path, payload in reversed(facts):
        _put_fact(
            right, source_id=source_id, revision=revision, upstream_path=path, payload=payload
        )

    assert materialize_solution_facts(collection, left) == materialize_solution_facts(
        collection, right
    )
