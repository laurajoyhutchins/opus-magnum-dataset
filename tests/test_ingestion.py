from __future__ import annotations

import hashlib
from pathlib import Path

from opus_corpus.ingestion import ObservedArtifactCandidate, ingest_artifacts


def _candidate(path: Path, **overrides: object) -> ObservedArtifactCandidate:
    values: dict[str, object] = {
        "artifact_kind": "solution",
        "puzzle_id": "om.puzzle.0001",
        "path": path,
        "artifact_format": "solution",
        "rights_status": "local_fetch_only",
        "source_id": "om-archive",
        "source_revision": "revision-a",
        "source_object_id": None,
        "source_path": "CHAPTER_1/P001/example.solution",
        "source_url": None,
        "author": "Example Author",
        "retrieved_at": "2026-08-24T12:00:00Z",
        "claimed_cost": 20,
        "claimed_cycles": 40,
        "claimed_area": 10,
        "claimed_instructions": 6,
    }
    values.update(overrides)
    return ObservedArtifactCandidate(**values)  # type: ignore[arg-type]


def test_ingest_solution_streams_exact_bytes_into_content_store(tmp_path: Path) -> None:
    source = tmp_path / "source.solution"
    payload = b"exact-solution-bytes\x00\xff\n"
    source.write_bytes(payload)
    object_root = tmp_path / "objects"
    digest = hashlib.sha256(payload).hexdigest()

    result = ingest_artifacts([_candidate(source)], object_root)

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_kind == "solution"
    assert artifact.artifact_id == f"om.solution.sha256.{digest}"
    assert artifact.puzzle_id == "om.puzzle.0001"
    assert artifact.sha256 == digest
    assert artifact.byte_length == len(payload)
    assert artifact.artifact_format == "solution"
    assert artifact.rights_status == "local_fetch_only"
    assert artifact.object_key == f"sha256/{digest[:2]}/{digest}"
    assert (object_root / artifact.object_key).read_bytes() == payload

    assert len(result.provenance) == 1
    provenance = result.provenance[0]
    assert provenance.artifact_id == artifact.artifact_id
    assert provenance.puzzle_id == "om.puzzle.0001"
    assert provenance.source_id == "om-archive"
    assert provenance.source_path == "CHAPTER_1/P001/example.solution"
    assert provenance.claimed_cost == 20
    assert provenance.rights_status == "local_fetch_only"


def test_ingest_puzzle_uses_distinct_artifact_namespace(tmp_path: Path) -> None:
    source = tmp_path / "source.puzzle"
    payload = b"exact-puzzle-bytes"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    result = ingest_artifacts(
        [
            _candidate(
                source,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="omsim",
                source_path="test/puzzle/P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            )
        ],
        tmp_path / "objects",
    )

    assert result.artifacts[0].artifact_id == f"om.puzzle-artifact.sha256.{digest}"
