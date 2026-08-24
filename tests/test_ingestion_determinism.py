from __future__ import annotations

from opus_corpus.ingestion import ArtifactProvenance, _provenance_sort_key


def _row(source_object_id: str | None) -> ArtifactProvenance:
    return ArtifactProvenance(
        artifact_id="om.solution.sha256." + "a" * 64,
        puzzle_id="om.puzzle.0001",
        source_role="artifact",
        source_id="source",
        source_revision="revision-a",
        source_path="path/a.solution",
        source_object_id=source_object_id,
        source_url=None,
        author=None,
        retrieved_at="2026-08-24T12:00:00+00:00",
        rights_status="local_fetch_only",
        observed_sha256="a" * 64,
        source_evidence_sha256="a" * 64,
        source_evidence_byte_length=1,
        claimed_cost=None,
        claimed_cycles=None,
        claimed_area=None,
        claimed_instructions=None,
    )


def test_provenance_sort_key_distinguishes_none_from_empty_string() -> None:
    assert _provenance_sort_key(_row(None)) != _provenance_sort_key(_row(""))
