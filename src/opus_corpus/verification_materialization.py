from __future__ import annotations

from collections.abc import Iterable

from .content_store import ContentStore, ContentStoreError
from .errors import CorpusError
from .hashing import sha256_bytes
from .ingestion import ArtifactRecord
from .verification import VerificationInput, VerificationResult, Verifier, verification_id


class VerificationMaterializationError(CorpusError):
    """Raised when canonical artifacts cannot be verified unambiguously."""


_EXPECTED_FORMAT = {"puzzle": "puzzle", "solution": "solution"}
_EXPECTED_ID_PREFIX = {
    "puzzle": "om.puzzle-artifact.sha256.",
    "solution": "om.solution.sha256.",
}


def _validate_artifact(record: ArtifactRecord) -> None:
    expected_format = _EXPECTED_FORMAT.get(record.artifact_kind)
    if expected_format is None:
        raise VerificationMaterializationError(
            f"unsupported verification artifact kind {record.artifact_kind!r}"
        )
    if record.artifact_format != expected_format:
        raise VerificationMaterializationError(
            f"{record.artifact_id}: expected {expected_format!r} artifact format, "
            f"got {record.artifact_format!r}"
        )
    expected_id = _EXPECTED_ID_PREFIX[record.artifact_kind] + record.sha256
    if record.artifact_id != expected_id:
        raise VerificationMaterializationError(
            f"{record.puzzle_id}: artifact identity does not match exact bytes"
        )


def _unique_artifacts(records: Iterable[ArtifactRecord]) -> tuple[ArtifactRecord, ...]:
    by_id: dict[str, ArtifactRecord] = {}
    for record in records:
        _validate_artifact(record)
        previous = by_id.setdefault(record.artifact_id, record)
        if previous != record:
            raise VerificationMaterializationError(
                f"conflicting canonical artifact facts for {record.artifact_id}"
            )
    return tuple(by_id[key] for key in sorted(by_id))


def _exact_bytes(
    store: ContentStore,
    record: ArtifactRecord,
    cache: dict[str, bytes],
) -> bytes:
    cached = cache.get(record.artifact_id)
    if cached is not None:
        return cached
    try:
        stored = store.require(record.sha256, record.byte_length)
        if stored.object_key != record.object_key:
            raise VerificationMaterializationError(
                f"{record.artifact_id}: content object key does not match canonical artifact"
            )
        payload = store.object_path(record.sha256).read_bytes()
    except (ContentStoreError, OSError) as exc:
        raise VerificationMaterializationError(str(exc)) from exc
    if len(payload) != record.byte_length or sha256_bytes(payload) != record.sha256:
        raise VerificationMaterializationError(
            f"content object changed while reading {record.artifact_id}"
        )
    cache[record.artifact_id] = payload
    return payload


def _validate_result(
    result: VerificationResult,
    *,
    puzzle: ArtifactRecord,
    solution: ArtifactRecord,
    validation_profile: str,
) -> None:
    if result.puzzle_artifact_id != puzzle.artifact_id:
        raise VerificationMaterializationError(
            f"{solution.artifact_id}: verifier returned the wrong puzzle artifact lineage"
        )
    if result.solution_id != solution.artifact_id:
        raise VerificationMaterializationError(
            f"{solution.artifact_id}: verifier returned the wrong solution artifact lineage"
        )
    if result.validation_profile != validation_profile:
        raise VerificationMaterializationError(
            f"{solution.artifact_id}: verifier returned the wrong validation profile"
        )
    expected_id = verification_id(
        puzzle_artifact_id=result.puzzle_artifact_id,
        solution_id=result.solution_id,
        verifier_implementation=result.verifier_implementation,
        verifier_revision=result.verifier_revision,
        verifier_sha256=result.verifier_sha256,
        validation_profile=result.validation_profile,
    )
    if result.verification_id != expected_id:
        raise VerificationMaterializationError(
            f"{solution.artifact_id}: verifier returned an invalid verification identity"
        )


def materialize_verifications(
    artifacts: Iterable[ArtifactRecord],
    *,
    store: ContentStore,
    verifier: Verifier,
    validation_profile: str,
) -> tuple[VerificationResult, ...]:
    """Verify canonical solution artifacts against their unique canonical puzzle bytes."""

    records = _unique_artifacts(artifacts)
    puzzle_by_id: dict[str, list[ArtifactRecord]] = {}
    solutions: list[ArtifactRecord] = []
    for record in records:
        if record.artifact_kind == "puzzle":
            puzzle_by_id.setdefault(record.puzzle_id, []).append(record)
        else:
            solutions.append(record)

    exact_bytes: dict[str, bytes] = {}
    results: list[VerificationResult] = []
    seen_verification_ids: set[str] = set()
    for solution in sorted(solutions, key=lambda row: row.artifact_id):
        puzzles = puzzle_by_id.get(solution.puzzle_id, [])
        if not puzzles:
            raise VerificationMaterializationError(
                f"{solution.puzzle_id}: no puzzle artifact for {solution.artifact_id}"
            )
        if len(puzzles) != 1:
            raise VerificationMaterializationError(
                f"{solution.puzzle_id}: multiple puzzle artifacts for {solution.artifact_id}"
            )
        puzzle = puzzles[0]
        value = VerificationInput(
            puzzle_artifact_id=puzzle.artifact_id,
            solution_id=solution.artifact_id,
            puzzle_bytes=_exact_bytes(store, puzzle, exact_bytes),
            solution_bytes=_exact_bytes(store, solution, exact_bytes),
            validation_profile=validation_profile,
        )
        result = verifier.verify(value)
        _validate_result(
            result,
            puzzle=puzzle,
            solution=solution,
            validation_profile=validation_profile,
        )
        if result.verification_id in seen_verification_ids:
            raise VerificationMaterializationError(
                f"duplicate verification identity {result.verification_id}"
            )
        seen_verification_ids.add(result.verification_id)
        results.append(result)

    return tuple(sorted(results, key=lambda row: row.verification_id))
