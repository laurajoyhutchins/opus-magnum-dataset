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
    source_id: str = "source-a",
    revision: str = "revision-a",
    upstream_path: str = "artifact.solution",
    rights_status: str = "local_fetch_only",
) -> CacheReceipt:
    stored = store.put_bytes(payload)
    return CacheReceipt(
        source_id=source_id,
        revision=revision,
        upstream_path=upstream_path,
        sha256=stored.sha256,
        byte_length=stored.byte_length,
        rights_status=rights_status,
        retrieved_at="2026-08-24T12:00:00+00:00",
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
        "author": None,
        "claimed_cost": None,
        "claimed_cycles": None,
        "claimed_area": None,
        "claimed_instructions": None,
    }
    values.update(overrides)
    return ObservedArtifactCandidate(**values)  # type: ignore[arg-type]


def test_identical_puzzle_bytes_deduplicate_without_losing_provenance(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(
        store,
        b"same puzzle",
        source_id="source-a",
        upstream_path="a.puzzle",
    )
    second = _receipt(
        store,
        b"same puzzle",
        source_id="source-b",
        upstream_path="b.puzzle",
    )

    result = ingest_artifacts(
        [
            _candidate(first, artifact_kind="puzzle", artifact_format="puzzle"),
            _candidate(second, artifact_kind="puzzle", artifact_format="puzzle"),
        ],
        store,
    )

    assert len(result.artifacts) == 1
    assert len(result.provenance) == 2
    assert {row.source_id for row in result.provenance} == {"source-a", "source-b"}


def test_artifact_rights_fold_preserves_per_source_provenance_rights(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    first = _receipt(
        store,
        b"same solution",
        source_id="source-a",
        upstream_path="a.solution",
        rights_status="redistributable",
    )
    second = _receipt(
        store,
        b"same solution",
        source_id="source-b",
        upstream_path="b.solution",
        rights_status="local_fetch_only",
    )

    result = ingest_artifacts([_candidate(first), _candidate(second)], store)

    assert result.artifacts[0].rights_status == "local_fetch_only"
    assert {(row.source_id, row.rights_status) for row in result.provenance} == {
        ("source-a", "redistributable"),
        ("source-b", "local_fetch_only"),
    }


def test_metadata_evidence_preserves_exact_byte_lengths(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"solution", upstream_path="a.solution")
    evidence = _receipt(store, b'{"cost":19}', upstream_path="a.json")

    result = ingest_artifacts(
        [_candidate(artifact, evidence_receipt=evidence, claimed_cost=19)],
        store,
    )

    artifact_row = next(row for row in result.provenance if row.source_role == "artifact")
    evidence_row = next(row for row in result.provenance if row.source_role == "evidence")
    assert artifact_row.source_evidence_byte_length == artifact.byte_length
    assert evidence_row.source_evidence_byte_length == evidence.byte_length


def test_evidence_revision_mismatch_fails_closed(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"artifact", revision="revision-a")
    evidence = _receipt(
        store,
        b"metadata",
        revision="revision-b",
        upstream_path="metadata.json",
    )

    with pytest.raises(ArtifactIngestionError, match="share artifact source and revision"):
        ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)


def test_corrupt_artifact_object_propagates_content_store_error(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    receipt = _receipt(store, b"artifact")
    store.object_path(receipt.sha256).write_bytes(b"corrupt!")

    with pytest.raises(ContentStoreError, match="corrupt content object"):
        ingest_artifacts([_candidate(receipt)], store)


def test_corrupt_evidence_object_propagates_content_store_error(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    artifact = _receipt(store, b"artifact", upstream_path="artifact.solution")
    evidence = _receipt(store, b"meta", upstream_path="metadata.json")
    store.object_path(evidence.sha256).write_bytes(b"oops")

    with pytest.raises(ContentStoreError, match="corrupt content object"):
        ingest_artifacts([_candidate(artifact, evidence_receipt=evidence)], store)
