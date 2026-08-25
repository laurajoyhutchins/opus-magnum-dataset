from __future__ import annotations

import struct
from pathlib import Path

import pytest

from opus_corpus.content_store import ContentStore
from opus_corpus.errors import CorpusError
from opus_corpus.ingestion import ArtifactRecord
from opus_corpus.puzzle_definition import reconcile_puzzle_definition


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def _string(value: bytes) -> bytes:
    assert len(value) < 0x80
    return bytes([len(value)]) + value


def _molecule(atom_type: int) -> bytes:
    return _u32(1) + bytes([atom_type, 0, 0]) + _u32(0)


def _puzzle(*, name: bytes, creator: int = 0, atom_type: int = 1) -> bytes:
    return b"".join(
        (
            _u32(3),
            _string(name),
            _u64(creator),
            _u64(0),
            _u32(1),
            _molecule(atom_type),
            _u32(1),
            _molecule(2),
            _u32(1),
            b"\x00",
        )
    )


def _artifact(store: ContentStore, payload: bytes, *, puzzle_id: str = "om.puzzle.0001"):
    stored = store.put_bytes(payload)
    return ArtifactRecord(
        artifact_kind="puzzle",
        artifact_id="om.puzzle-artifact.sha256." + stored.sha256,
        puzzle_id=puzzle_id,
        sha256=stored.sha256,
        byte_length=stored.byte_length,
        artifact_format="puzzle",
        rights_status="local_fetch_only",
        object_key=stored.object_key,
    )


def _observation(
    artifact: ArtifactRecord,
    observation_id: str,
    *,
    source_role: str = "artifact",
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "artifact_kind": "puzzle",
        "artifact_id": artifact.artifact_id,
        "puzzle_id": artifact.puzzle_id,
        "source_role": source_role,
        "observed_sha256": artifact.sha256,
    }


def test_materializes_semantics_from_authoritative_content_store(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifact_semantic_evidence

    store = ContentStore(tmp_path / "store")
    artifact = _artifact(store, _puzzle(name=b"Alpha"))

    result = materialize_puzzle_artifact_semantic_evidence(
        [artifact],
        [_observation(artifact, "obs-a")],
        store,
    )

    assert len(result) == 1
    assert result[0].puzzle_id == "om.puzzle.0001"
    assert result[0].puzzle_artifact_id == artifact.artifact_id
    assert result[0].observation_ids == ("obs-a",)
    assert result[0].claims["reagents"][0]["atoms"][0]["atom_type"] == "salt"


def test_decoded_semantics_only_cite_observations_that_expose_exact_bytes(
    tmp_path: Path,
) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifact_semantic_evidence

    store = ContentStore(tmp_path / "store")
    artifact = _artifact(store, _puzzle(name=b"Alpha"))
    result = materialize_puzzle_artifact_semantic_evidence(
        [artifact],
        [
            _observation(artifact, "obs-artifact", source_role="artifact"),
            _observation(artifact, "obs-manifest", source_role="metadata"),
        ],
        store,
    )

    assert result[0].observation_ids == ("obs-artifact",)


def test_requires_artifact_provenance_observation(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifact_semantic_evidence

    store = ContentStore(tmp_path / "store")
    artifact = _artifact(store, _puzzle(name=b"Alpha"))

    with pytest.raises(CorpusError, match="no matching artifact observation"):
        materialize_puzzle_artifact_semantic_evidence([artifact], [], store)


def test_rejects_observation_with_wrong_exact_hash(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifact_semantic_evidence

    store = ContentStore(tmp_path / "store")
    artifact = _artifact(store, _puzzle(name=b"Alpha"))
    observation = _observation(artifact, "obs-a")
    observation["observed_sha256"] = "0" * 64

    with pytest.raises(CorpusError, match="observation sha256"):
        materialize_puzzle_artifact_semantic_evidence([artifact], [observation], store)


def test_rejects_artifact_object_key_not_bound_to_store(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifact_semantic_evidence

    store = ContentStore(tmp_path / "store")
    good = _artifact(store, _puzzle(name=b"Alpha"))
    artifact = ArtifactRecord(
        artifact_kind=good.artifact_kind,
        artifact_id=good.artifact_id,
        puzzle_id=good.puzzle_id,
        sha256=good.sha256,
        byte_length=good.byte_length,
        artifact_format=good.artifact_format,
        rights_status=good.rights_status,
        object_key="objects/sha256/00/not-the-object",
    )

    with pytest.raises(CorpusError, match="object key"):
        materialize_puzzle_artifact_semantic_evidence(
            [artifact],
            [_observation(artifact, "obs-a")],
            store,
        )


def test_byte_distinct_artifacts_can_support_one_semantic_definition(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifact_semantic_evidence

    store = ContentStore(tmp_path / "store")
    first = _artifact(store, _puzzle(name=b"Alpha", creator=1))
    second = _artifact(store, _puzzle(name=b"Different serialization metadata", creator=2))
    assert first.artifact_id != second.artifact_id

    evidence = materialize_puzzle_artifact_semantic_evidence(
        [first, second],
        [_observation(first, "obs-a"), _observation(second, "obs-b")],
        store,
    )
    resolution = reconcile_puzzle_definition("om.puzzle.0001", evidence)

    assert resolution.definition is not None
    assert resolution.puzzle_artifact_ids == tuple(sorted((first.artifact_id, second.artifact_id)))
    assert resolution.source_observation_ids == ("obs-a", "obs-b")


def test_byte_distinct_semantic_disagreement_fails_shared_reconciliation(tmp_path: Path) -> None:
    from opus_corpus.puzzle_materialization import materialize_puzzle_artifact_semantic_evidence

    store = ContentStore(tmp_path / "store")
    first = _artifact(store, _puzzle(name=b"Alpha", atom_type=1))
    second = _artifact(store, _puzzle(name=b"Beta", atom_type=3))

    evidence = materialize_puzzle_artifact_semantic_evidence(
        [first, second],
        [_observation(first, "obs-a"), _observation(second, "obs-b")],
        store,
    )
    with pytest.raises(CorpusError, match="conflicting semantic evidence.*reagents"):
        reconcile_puzzle_definition("om.puzzle.0001", evidence)
