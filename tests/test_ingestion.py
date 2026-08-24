from __future__ import annotations

from pathlib import Path

from opus_corpus.cache import CacheReceipt
from opus_corpus.content_store import ContentStore
from opus_corpus.ingestion import ObservedArtifactCandidate, ingest_artifacts


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
