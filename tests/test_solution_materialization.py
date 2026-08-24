from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from opus_corpus.cache import CacheReceipt, ContentAddressedCache
from opus_corpus.content_store import ContentStore, ContentStoreError

try:
    from opus_corpus.solution_materialization import (
        SolutionMaterializationError,
        materialize_solution_facts,
    )
except ModuleNotFoundError:
    SolutionMaterializationError = None  # type: ignore[assignment]
    materialize_solution_facts = None  # type: ignore[assignment]


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


def _leaderboard_metadata(data_path: str, *, cost: int = 100) -> bytes:
    return json.dumps(
        {
            "puzzle": "STABILIZED_WATER",
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


def _require_materializer() -> None:
    assert materialize_solution_facts is not None, "WP-04 materializer is not implemented"
    assert SolutionMaterializationError is not None


def test_identical_cross_source_solution_bytes_deduplicate_but_keep_observations(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    _require_materializer()
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
    assert metadata.source_object_id == leaderboard_path
    assert metadata.source_url == "https://zlbb.example/solution"


def test_unpaired_leaderboard_metadata_is_preserved_as_observation(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    _require_materializer()
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
    assert observation.source_object_id == missing_path
    assert observation.claimed_cost == 7
    assert observation.observed_sha256 is None
    assert observation.source_evidence_sha256 == metadata_receipt.sha256


def test_relative_data_path_pairs_with_solution_in_same_directory(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    _require_materializer()
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


def test_metadata_data_path_cannot_escape_its_puzzle_directory(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    _require_materializer()
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
    _require_materializer()
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


def test_corrupt_solution_object_fails_closed(
    tmp_path: Path, collection: FixtureCollection
) -> None:
    _require_materializer()
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
    _require_materializer()
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
