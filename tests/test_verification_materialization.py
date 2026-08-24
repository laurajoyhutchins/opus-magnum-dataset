from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from opus_corpus.content_store import ContentStore
from opus_corpus.ingestion import ArtifactRecord
from opus_corpus.verification import (
    VerificationInput,
    VerificationResult,
    verification_id,
)
from opus_corpus.verification_materialization import (
    VerificationMaterializationError,
    materialize_verifications,
)


@dataclass
class RecordingVerifier:
    calls: list[VerificationInput] = field(default_factory=list)

    def verify(self, value: VerificationInput) -> VerificationResult:
        self.calls.append(value)
        identity = {
            "puzzle_artifact_id": value.puzzle_artifact_id,
            "solution_id": value.solution_id,
            "verifier_implementation": "fixture-verifier",
            "verifier_revision": "fixture-v1",
            "verifier_sha256": None,
            "validation_profile": value.validation_profile,
        }
        return VerificationResult(
            verification_id=verification_id(**identity),
            puzzle_artifact_id=value.puzzle_artifact_id,
            solution_id=value.solution_id,
            verifier_implementation="fixture-verifier",
            verifier_revision="fixture-v1",
            verifier_sha256=None,
            validation_profile=value.validation_profile,
            parse_status="passed",
            simulation_status="passed",
            cost=1,
            cycles=2,
            area=3,
            instructions=4,
            vanilla_constructible=None,
            record_eligible=None,
            error_code=None,
            error_detail=None,
        )


def artifact(
    store: ContentStore,
    *,
    kind: str,
    puzzle_id: str,
    payload: bytes,
    artifact_format: str | None = None,
) -> ArtifactRecord:
    stored = store.put_bytes(payload)
    prefix = {
        "puzzle": "om.puzzle-artifact.sha256.",
        "solution": "om.solution.sha256.",
    }.get(kind, f"om.{kind}.sha256.")
    return ArtifactRecord(
        artifact_kind=kind,
        artifact_id=prefix + stored.sha256,
        puzzle_id=puzzle_id,
        sha256=stored.sha256,
        byte_length=stored.byte_length,
        artifact_format=artifact_format or kind,
        rights_status="local_fetch_only",
        object_key=stored.object_key,
    )


def test_materialization_pairs_exact_artifact_bytes_and_is_input_order_independent(tmp_path):
    store = ContentStore(tmp_path / "cache")
    puzzle = artifact(store, kind="puzzle", puzzle_id="om.puzzle.1", payload=b"puzzle-bytes")
    solution_a = artifact(
        store,
        kind="solution",
        puzzle_id="om.puzzle.1",
        payload=b"solution-a",
    )
    solution_b = artifact(
        store,
        kind="solution",
        puzzle_id="om.puzzle.1",
        payload=b"solution-b",
    )

    first_verifier = RecordingVerifier()
    first = materialize_verifications(
        [solution_b, puzzle, solution_a],
        store=store,
        verifier=first_verifier,
        validation_profile="fixture-profile",
    )
    second_verifier = RecordingVerifier()
    second = materialize_verifications(
        [solution_a, puzzle, solution_b],
        store=store,
        verifier=second_verifier,
        validation_profile="fixture-profile",
    )

    assert first == second
    assert tuple(row.verification_id for row in first) == tuple(
        sorted(row.verification_id for row in first)
    )
    assert first_verifier.calls == second_verifier.calls
    assert {call.solution_bytes for call in first_verifier.calls} == {b"solution-a", b"solution-b"}
    assert {call.puzzle_bytes for call in first_verifier.calls} == {b"puzzle-bytes"}
    assert {call.puzzle_artifact_id for call in first_verifier.calls} == {puzzle.artifact_id}
    assert {call.solution_id for call in first_verifier.calls} == {
        solution_a.artifact_id,
        solution_b.artifact_id,
    }


def test_materialization_fails_when_solution_has_no_puzzle_artifact(tmp_path):
    store = ContentStore(tmp_path / "cache")
    solution = artifact(store, kind="solution", puzzle_id="om.puzzle.1", payload=b"solution")

    with pytest.raises(VerificationMaterializationError, match="no puzzle artifact"):
        materialize_verifications(
            [solution],
            store=store,
            verifier=RecordingVerifier(),
            validation_profile="fixture-profile",
        )


def test_materialization_fails_when_puzzle_identity_is_ambiguous(tmp_path):
    store = ContentStore(tmp_path / "cache")
    puzzle_a = artifact(store, kind="puzzle", puzzle_id="om.puzzle.1", payload=b"puzzle-a")
    puzzle_b = artifact(store, kind="puzzle", puzzle_id="om.puzzle.1", payload=b"puzzle-b")
    solution = artifact(store, kind="solution", puzzle_id="om.puzzle.1", payload=b"solution")

    with pytest.raises(VerificationMaterializationError, match="multiple puzzle artifacts"):
        materialize_verifications(
            [puzzle_a, solution, puzzle_b],
            store=store,
            verifier=RecordingVerifier(),
            validation_profile="fixture-profile",
        )


@pytest.mark.parametrize(
    "record",
    [
        ArtifactRecord(
            artifact_kind="observation",
            artifact_id="om.observation.sha256." + "1" * 64,
            puzzle_id="om.puzzle.1",
            sha256="1" * 64,
            byte_length=1,
            artifact_format="json",
            rights_status="local_fetch_only",
            object_key="objects/sha256/11/" + "1" * 62,
        ),
        ArtifactRecord(
            artifact_kind="puzzle",
            artifact_id="om.puzzle-artifact.sha256." + "2" * 64,
            puzzle_id="om.puzzle.1",
            sha256="2" * 64,
            byte_length=1,
            artifact_format="json",
            rights_status="local_fetch_only",
            object_key="objects/sha256/22/" + "2" * 62,
        ),
        ArtifactRecord(
            artifact_kind="solution",
            artifact_id="om.solution.sha256." + "3" * 64,
            puzzle_id="om.puzzle.1",
            sha256="3" * 64,
            byte_length=1,
            artifact_format="json",
            rights_status="local_fetch_only",
            object_key="objects/sha256/33/" + "3" * 62,
        ),
    ],
)
def test_materialization_rejects_non_verifier_artifact_shapes(tmp_path, record: ArtifactRecord):
    store = ContentStore(tmp_path / "cache")

    with pytest.raises(VerificationMaterializationError):
        materialize_verifications(
            [record],
            store=store,
            verifier=RecordingVerifier(),
            validation_profile="fixture-profile",
        )


def test_materialization_wraps_content_corruption_at_its_boundary(tmp_path):
    store = ContentStore(tmp_path / "cache")
    puzzle = artifact(store, kind="puzzle", puzzle_id="om.puzzle.1", payload=b"puzzle")
    solution = artifact(store, kind="solution", puzzle_id="om.puzzle.1", payload=b"solution")
    store.object_path(solution.sha256).write_bytes(b"corrupt!")

    with pytest.raises(VerificationMaterializationError, match="content object"):
        materialize_verifications(
            [puzzle, solution],
            store=store,
            verifier=RecordingVerifier(),
            validation_profile="fixture-profile",
        )
