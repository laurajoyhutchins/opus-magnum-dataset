from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import opus_corpus.ingestion as ingestion
from opus_corpus.ingestion import (
    ArtifactIngestionError,
    ObservedArtifactCandidate,
    ingest_artifacts,
)


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


def test_identical_solution_bytes_deduplicate_without_losing_provenance(tmp_path: Path) -> None:
    first = tmp_path / "first.solution"
    second = tmp_path / "second.solution"
    first.write_bytes(b"same bytes")
    second.write_bytes(b"same bytes")

    result = ingest_artifacts(
        [
            _candidate(first, source_id="om-archive", source_path="archive/a.solution"),
            _candidate(
                second,
                source_id="om-leaderboard",
                source_path="leaderboard/a.solution",
                claimed_cost=19,
            ),
        ],
        tmp_path / "objects",
    )

    assert len(result.artifacts) == 1
    assert len(result.provenance) == 2
    assert {row.source_id for row in result.provenance} == {"om-archive", "om-leaderboard"}
    assert {row.claimed_cost for row in result.provenance} == {19, 20}
    assert not hasattr(result.artifacts[0], "claimed_cost")


def test_identical_puzzle_bytes_deduplicate_without_losing_provenance(tmp_path: Path) -> None:
    first = tmp_path / "first.puzzle"
    second = tmp_path / "second.puzzle"
    first.write_bytes(b"same puzzle")
    second.write_bytes(b"same puzzle")

    result = ingest_artifacts(
        [
            _candidate(
                first,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="omsim",
                source_path="fixtures/P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            ),
            _candidate(
                second,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="official-game",
                source_path="P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            ),
        ],
        tmp_path / "objects",
    )

    assert len(result.artifacts) == 1
    assert {row.source_id for row in result.provenance} == {"omsim", "official-game"}


def test_exact_duplicate_provenance_assertions_collapse(tmp_path: Path) -> None:
    source = tmp_path / "same.solution"
    source.write_bytes(b"same bytes")
    candidate = _candidate(source)

    result = ingest_artifacts([candidate, candidate], tmp_path / "objects")

    assert len(result.artifacts) == 1
    assert len(result.provenance) == 1


def test_different_bytes_never_deduplicate(tmp_path: Path) -> None:
    first = tmp_path / "first.solution"
    second = tmp_path / "second.solution"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    result = ingest_artifacts(
        [_candidate(first), _candidate(second, source_path="other.solution")],
        tmp_path / "objects",
    )

    assert len(result.artifacts) == 2


def test_artifact_rights_local_fetch_only_outranks_other_statuses(tmp_path: Path) -> None:
    sources = [tmp_path / name for name in ("a.solution", "b.solution", "c.solution")]
    for source in sources:
        source.write_bytes(b"same")

    result = ingest_artifacts(
        [
            _candidate(sources[0], source_id="a", source_path="a", rights_status="redistributable"),
            _candidate(sources[1], source_id="b", source_path="b", rights_status="unknown"),
            _candidate(
                sources[2],
                source_id="c",
                source_path="c",
                rights_status="local_fetch_only",
            ),
        ],
        tmp_path / "objects",
    )

    assert result.artifacts[0].rights_status == "local_fetch_only"
    assert {row.rights_status for row in result.provenance} == {
        "redistributable",
        "unknown",
        "local_fetch_only",
    }


def test_artifact_rights_unknown_outranks_redistributable(tmp_path: Path) -> None:
    first = tmp_path / "a.solution"
    second = tmp_path / "b.solution"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    result = ingest_artifacts(
        [
            _candidate(first, source_id="a", source_path="a", rights_status="redistributable"),
            _candidate(second, source_id="b", source_path="b", rights_status="unknown"),
        ],
        tmp_path / "objects",
    )

    assert result.artifacts[0].rights_status == "unknown"


def test_logical_output_is_independent_of_candidate_and_local_path_order(tmp_path: Path) -> None:
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    left_root.mkdir()
    right_root.mkdir()
    (left_root / "a.solution").write_bytes(b"alpha")
    (left_root / "b.solution").write_bytes(b"beta")
    (right_root / "renamed-one.solution").write_bytes(b"alpha")
    (right_root / "renamed-two.solution").write_bytes(b"beta")

    left = ingest_artifacts(
        [
            _candidate(left_root / "b.solution", source_id="b", source_path="stable/b"),
            _candidate(left_root / "a.solution", source_id="a", source_path="stable/a"),
        ],
        tmp_path / "objects-left",
    )
    right = ingest_artifacts(
        [
            _candidate(right_root / "renamed-one.solution", source_id="a", source_path="stable/a"),
            _candidate(right_root / "renamed-two.solution", source_id="b", source_path="stable/b"),
        ],
        tmp_path / "objects-right",
    )

    assert left == right


def test_same_solution_digest_for_different_puzzles_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "a.solution"
    second = tmp_path / "b.solution"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    with pytest.raises(ArtifactIngestionError, match="different puzzle IDs"):
        ingest_artifacts(
            [
                _candidate(first, puzzle_id="om.puzzle.0001"),
                _candidate(second, puzzle_id="om.puzzle.0002", source_path="b.solution"),
            ],
            tmp_path / "objects",
        )


def test_same_puzzle_digest_for_different_puzzles_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "a.puzzle"
    second = tmp_path / "b.puzzle"
    first.write_bytes(b"same puzzle bytes")
    second.write_bytes(b"same puzzle bytes")

    with pytest.raises(ArtifactIngestionError, match="different puzzle IDs"):
        ingest_artifacts(
            [
                _candidate(
                    first,
                    artifact_kind="puzzle",
                    artifact_format="puzzle",
                    puzzle_id="om.puzzle.0001",
                    claimed_cost=None,
                    claimed_cycles=None,
                    claimed_area=None,
                    claimed_instructions=None,
                ),
                _candidate(
                    second,
                    artifact_kind="puzzle",
                    artifact_format="puzzle",
                    puzzle_id="om.puzzle.0002",
                    source_path="b.puzzle",
                    claimed_cost=None,
                    claimed_cycles=None,
                    claimed_area=None,
                    claimed_instructions=None,
                ),
            ],
            tmp_path / "objects",
        )


def test_same_artifact_digest_with_conflicting_formats_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "a.solution"
    second = tmp_path / "b.solution"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    with pytest.raises(ArtifactIngestionError, match="conflicting artifact formats"):
        ingest_artifacts(
            [
                _candidate(first, artifact_format="solution"),
                _candidate(second, artifact_format="legacy-solution", source_path="b.solution"),
            ],
            tmp_path / "objects",
        )


def test_same_bytes_in_puzzle_and_solution_namespaces_share_object_not_id(tmp_path: Path) -> None:
    puzzle = tmp_path / "a.puzzle"
    solution = tmp_path / "a.solution"
    puzzle.write_bytes(b"identical physical bytes")
    solution.write_bytes(b"identical physical bytes")

    result = ingest_artifacts(
        [
            _candidate(
                puzzle,
                artifact_kind="puzzle",
                artifact_format="puzzle",
                source_id="omsim",
                source_path="puzzle/P007.puzzle",
                claimed_cost=None,
                claimed_cycles=None,
                claimed_area=None,
                claimed_instructions=None,
            ),
            _candidate(solution, source_path="solution/P007.solution"),
        ],
        tmp_path / "objects",
    )

    by_kind = {artifact.artifact_kind: artifact for artifact in result.artifacts}
    assert set(by_kind) == {"puzzle", "solution"}
    assert by_kind["puzzle"].artifact_id != by_kind["solution"].artifact_id
    assert by_kind["puzzle"].sha256 == by_kind["solution"].sha256
    assert by_kind["puzzle"].object_key == by_kind["solution"].object_key


def test_missing_payload_fails_explicitly(tmp_path: Path) -> None:
    with pytest.raises(ArtifactIngestionError, match="cannot stat source payload"):
        ingest_artifacts([_candidate(tmp_path / "missing.solution")], tmp_path / "objects")


def test_directory_payload_fails_explicitly(tmp_path: Path) -> None:
    source = tmp_path / "directory"
    source.mkdir()
    with pytest.raises(ArtifactIngestionError, match="not a file"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")


def test_unreadable_payload_is_wrapped_as_ingestion_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.solution"
    source.write_bytes(b"payload")
    real_open = Path.open

    def fail_source_open(self: Path, *args: object, **kwargs: object):
        if self == source:
            raise PermissionError("denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_source_open)

    with pytest.raises(ArtifactIngestionError, match="cannot ingest source payload"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")


def test_corrupt_existing_content_object_fails_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.solution"
    source.write_bytes(b"good bytes")
    digest = hashlib.sha256(b"good bytes").hexdigest()
    object_path = tmp_path / "objects" / f"sha256/{digest[:2]}/{digest}"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"corrupt bytes")

    with pytest.raises(ArtifactIngestionError, match="does not match its digest"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")

    assert object_path.read_bytes() == b"corrupt bytes"


def test_source_change_during_stream_fails_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.solution"
    source.write_bytes(b"payload")
    original = ingestion._source_signature(source)
    changed = (original[0], original[1], original[2], original[3], original[4] + 1)
    signatures = iter((original, changed))

    monkeypatch.setattr(ingestion, "_source_signature", lambda path: next(signatures))

    with pytest.raises(ArtifactIngestionError, match="changed during ingestion"):
        ingest_artifacts([_candidate(source)], tmp_path / "objects")

    digest = hashlib.sha256(b"payload").hexdigest()
    assert not (tmp_path / "objects" / f"sha256/{digest[:2]}/{digest}").exists()
