from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.cache import CacheReceipt
from opus_corpus.content_store import ContentStore, ContentStoreError
from opus_corpus.ingestion import (
    ArtifactIngestionError,
    ObservedArtifactCandidate,
    ingest_artifacts,
)


def _receipt(
    store: ContentStore,
    payload: bytes,
    *,
    source_id: str = "om-archive",
    revision: str = "revision-a",
    upstream_path: str = "CHAPTER_1/P001/example.solution",
    rights_status: str = "local_fetch_only",
    retrieved_at: str = "2026-08-24T12:00:00+00:00",
) -> CacheReceipt:
    stored = store.put_bytes(payload)
    return CacheReceipt(
        source_id=source_id,
        revision=revision,
        upstream_path=upstream_path,
        sha256=stored.sha256,
        byte_length=stored.byte_length,
        rights_status=rights_status,
        retrieved_at=retrieved_at,
    )


def _candidate(receipt: CacheReceipt, **overrides: object) -> ObservedArtifactCandidate:
    values: dict[str, object] = {
        "artifact_kind": "solution",
        "puzzle_id": "om.puzzle.0001",
        "artifact_format": "solution",
        "artifact_receipt": receipt,
        "evidence_receipt": None,
        "source_object_id": None,
        "source_url": None,
        "author": "Example Author",
        "claimed_cost": 20,
        "claimed_cycles": 40,
        "claimed_area": 10,
        "claimed_instructions": 6,
    }
    values.update(overrides)
    return ObservedArtifactCandidate(**values)  # type: ignore[arg-type]


def test_solution_identity_comes_from_receipt_digest(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"solution bytes")

    result = ingest_artifacts([_candidate(receipt)], store)

    artifact = result.artifacts[0]
    assert artifact.artifact_id == f"om.solution.sha256.{receipt.sha256}"
    assert artifact.object_key == f"objects/sha256/{receipt.sha256[:2]}/{receipt.sha256[2:]}"


def test_puzzle_identity_uses_distinct_namespace(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"puzzle bytes", upstream_path="test/puzzle/P007.puzzle")

    result = ingest_artifacts(
        [_candidate(receipt, artifact_kind="puzzle", artifact_format="puzzle")], store
    )

    assert result.artifacts[0].artifact_id == f"om.puzzle-artifact.sha256.{receipt.sha256}"


def test_identical_bytes_deduplicate_without_losing_provenance(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"same", source_id="a", upstream_path="a.solution")
    second = _receipt(store, b"same", source_id="b", upstream_path="b.solution")

    result = ingest_artifacts([_candidate(first), _candidate(second, claimed_cost=19)], store)

    assert len(result.artifacts) == 1
    assert len(result.provenance) == 2
    assert {row.source_id for row in result.provenance} == {"a", "b"}
    assert not hasattr(result.artifacts[0], "claimed_cost")


def test_exact_duplicate_provenance_collapses(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"same")
    candidate = _candidate(receipt)

    result = ingest_artifacts([candidate, candidate], store)

    assert len(result.artifacts) == 1
    assert len(result.provenance) == 1


def test_distinct_bytes_never_deduplicate(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"first", upstream_path="first.solution")
    second = _receipt(store, b"second", upstream_path="second.solution")

    result = ingest_artifacts([_candidate(first), _candidate(second)], store)

    assert len(result.artifacts) == 2


def test_distinct_metadata_evidence_emits_second_provenance_fact(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(
        store,
        b"solution",
        source_id="om-leaderboard",
        upstream_path="P/a.solution",
    )
    evidence = _receipt(
        store,
        b'{"cost":19}',
        source_id="om-leaderboard",
        upstream_path="P/a.json",
    )

    result = ingest_artifacts(
        [_candidate(artifact, evidence_receipt=evidence, claimed_cost=19)], store
    )

    assert len(result.provenance) == 2
    artifact_row = next(row for row in result.provenance if row.source_role == "artifact")
    evidence_row = next(row for row in result.provenance if row.source_role == "evidence")
    assert artifact_row.source_path.endswith("a.solution")
    assert artifact_row.claimed_cost is None
    assert evidence_row.source_path.endswith("a.json")
    assert evidence_row.claimed_cost == 19
    assert evidence_row.observed_sha256 == artifact.sha256
    assert evidence_row.source_evidence_sha256 == evidence.sha256


def test_same_receipt_as_evidence_emits_one_provenance_fact(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"solution")

    result = ingest_artifacts([_candidate(receipt, claimed_cost=20)], store)

    assert len(result.provenance) == 1
    assert result.provenance[0].source_role == "artifact"
    assert result.provenance[0].claimed_cost == 20


def test_artifact_rights_ignore_more_restrictive_metadata_rights(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"same", rights_status="redistributable")
    evidence = _receipt(
        store,
        b"meta",
        upstream_path="a.json",
        rights_status="local_fetch_only",
    )

    result = ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)

    assert result.artifacts[0].rights_status == "redistributable"
    assert {row.rights_status for row in result.provenance} == {
        "redistributable",
        "local_fetch_only",
    }


def test_artifact_rights_fold_is_conservative(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipts = [
        _receipt(
            store,
            b"same",
            source_id="a",
            upstream_path="a",
            rights_status="redistributable",
        ),
        _receipt(
            store,
            b"same",
            source_id="b",
            upstream_path="b",
            rights_status="unknown",
        ),
        _receipt(
            store,
            b"same",
            source_id="c",
            upstream_path="c",
            rights_status="local_fetch_only",
        ),
    ]

    result = ingest_artifacts([_candidate(receipt) for receipt in receipts], store)

    assert result.artifacts[0].rights_status == "local_fetch_only"


def test_invalid_evidence_rights_fail_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"artifact")
    evidence = _receipt(
        store,
        b"meta",
        upstream_path="a.json",
        rights_status="invented",
    )

    with pytest.raises(ArtifactIngestionError, match="invalid rights status"):
        ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)


def test_candidate_order_and_cache_root_do_not_change_output(tmp_path: Path) -> None:
    left = ContentStore(tmp_path / "left")
    right = ContentStore(tmp_path / "right")
    left_a = _receipt(left, b"alpha", source_id="a", upstream_path="stable/a")
    left_b = _receipt(left, b"beta", source_id="b", upstream_path="stable/b")
    right_a = _receipt(right, b"alpha", source_id="a", upstream_path="stable/a")
    right_b = _receipt(right, b"beta", source_id="b", upstream_path="stable/b")

    left_result = ingest_artifacts([_candidate(left_b), _candidate(left_a)], left)
    right_result = ingest_artifacts([_candidate(right_a), _candidate(right_b)], right)

    assert left_result == right_result


def test_same_digest_for_different_puzzles_fails_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"same", source_id="a", upstream_path="a")
    second = _receipt(store, b"same", source_id="b", upstream_path="b")

    with pytest.raises(ArtifactIngestionError, match="different puzzle IDs"):
        ingest_artifacts(
            [_candidate(first), _candidate(second, puzzle_id="om.puzzle.0002")],
            store,
        )


def test_conflicting_formats_fail_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"same", source_id="a", upstream_path="a")
    second = _receipt(store, b"same", source_id="b", upstream_path="b")

    with pytest.raises(ArtifactIngestionError, match="conflicting artifact formats"):
        ingest_artifacts(
            [_candidate(first), _candidate(second, artifact_format="legacy-solution")],
            store,
        )


def test_same_artifact_receipt_identity_cannot_change_association(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"same")

    with pytest.raises(
        ArtifactIngestionError,
        match="artifact receipt identity has conflicting association",
    ):
        ingest_artifacts(
            [_candidate(receipt), _candidate(receipt, puzzle_id="om.puzzle.0002")],
            store,
        )


def test_evidence_assertion_identity_cannot_support_two_artifacts(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(store, b"first", upstream_path="first.solution")
    second = _receipt(store, b"second", upstream_path="second.solution")
    evidence = _receipt(store, b"meta", upstream_path="scores.json")

    with pytest.raises(ArtifactIngestionError, match="supports multiple artifacts"):
        ingest_artifacts(
            [
                _candidate(first, evidence_receipt=evidence, source_object_id="row-1"),
                _candidate(second, evidence_receipt=evidence, source_object_id="row-1"),
            ],
            store,
        )


def test_cross_source_attached_evidence_fails_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"artifact", source_id="a")
    evidence = _receipt(store, b"meta", source_id="b", upstream_path="meta.json")

    with pytest.raises(ArtifactIngestionError, match="share artifact source and revision"):
        ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)


def test_puzzle_and_solution_namespaces_share_object_not_identity(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    puzzle_receipt = _receipt(
        store,
        b"identical",
        upstream_path="puzzle/P007.puzzle",
    )
    solution_receipt = _receipt(
        store,
        b"identical",
        upstream_path="solution/P007.solution",
    )

    result = ingest_artifacts(
        [
            _candidate(
                puzzle_receipt,
                artifact_kind="puzzle",
                artifact_format="puzzle",
            ),
            _candidate(solution_receipt),
        ],
        store,
    )
    by_kind = {row.artifact_kind: row for row in result.artifacts}

    assert by_kind["puzzle"].artifact_id != by_kind["solution"].artifact_id
    assert by_kind["puzzle"].sha256 == by_kind["solution"].sha256
    assert by_kind["puzzle"].object_key == by_kind["solution"].object_key


def test_missing_object_propagates_content_store_error(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"artifact")
    store.object_path(receipt.sha256).unlink()

    with pytest.raises(ContentStoreError, match="missing content object"):
        ingest_artifacts([_candidate(receipt)], store)
