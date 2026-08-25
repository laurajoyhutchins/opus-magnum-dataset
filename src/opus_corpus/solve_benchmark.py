from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .benchmark_candidate import (
    CANDIDATE_OUTPUT_COMPILER,
    CANDIDATE_OUTPUT_COMPILER_VERSION,
    CandidateOutputCompileError,
    PuzzleSolutionMismatchError,
    compile_candidate_output,
    parse_candidate_solution,
)
from .benchmark_eligibility import (
    ELIGIBILITY_PROFILE,
    ELIGIBILITY_VERSION,
    BenchmarkEligibilityEntry,
    BenchmarkEligibilityProjection,
)
from .benchmark_results import (
    BenchmarkIdentity,
    BenchmarkRunIdentity,
    aggregate_benchmark_report,
    benchmark_id,
    benchmark_run_id,
    build_attempt_result,
    build_puzzle_result,
)
from .collections import CollectionDefinition
from .errors import CorpusError
from .hashing import canonical_json_bytes, sha256_bytes
from .puzzle_definition import validate_puzzle_definition
from .serialization import ModelPuzzleTextSerializer
from .solution_parser import SolutionParseError
from .verification import VerificationInput, VerificationResult, Verifier, VerifierIdentity, verification_id

PROTOCOL_VERSION = "solve-v0.1"
ATTEMPT_PROFILE = "bounded-sequential-v1"
SCORING_VERSION = "solve-report-v1"
HARNESS_IMPLEMENTATION = "opus-corpus-solve-harness"
HARNESS_REVISION = "1"


class SolveBenchmarkError(CorpusError):
    """Raised when authoritative benchmark inputs cannot produce a safe Solve run."""


@dataclass(frozen=True, slots=True)
class SolverIdentity:
    system_id: str
    system_revision: str
    generation_config_sha256: str | None


@dataclass(frozen=True, slots=True)
class RunnerOutput:
    raw_output: str
    model_calls: int | None = 1
    input_tokens: int | None = None
    output_tokens: int | None = None


class SolveRunner(Protocol):
    identity: SolverIdentity

    def generate(
        self,
        *,
        puzzle_id: str,
        puzzle_text: str,
        attempt_index: int,
    ) -> RunnerOutput: ...


@dataclass(frozen=True, slots=True)
class SolveBenchmarkResult:
    eligibility: BenchmarkEligibilityProjection
    puzzle_results: tuple[dict[str, Any], ...]
    report: dict[str, Any]


def _collection_rows(collection: CollectionDefinition) -> dict[str, Mapping[str, str]]:
    rows: dict[str, Mapping[str, str]] = {}
    for row in collection.inventory_rows:
        puzzle_id = row.get("puzzle_id")
        if not isinstance(puzzle_id, str) or not puzzle_id:
            raise SolveBenchmarkError("collection contains an invalid puzzle_id")
        if puzzle_id in rows:
            raise SolveBenchmarkError(f"duplicate collection puzzle {puzzle_id}")
        rows[puzzle_id] = row
    return rows


def _definitions_by_puzzle(
    definitions: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for value in definitions:
        record = dict(value)
        try:
            validate_puzzle_definition(record)
        except Exception as exc:
            raise SolveBenchmarkError(f"invalid puzzle definition: {exc}") from exc
        puzzle_id = record["puzzle_id"]
        if puzzle_id in rows:
            raise SolveBenchmarkError(f"duplicate puzzle definition for {puzzle_id}")
        rows[puzzle_id] = record
    return rows


def _validate_projection(
    collection: CollectionDefinition,
    eligibility: BenchmarkEligibilityProjection,
) -> None:
    if eligibility.profile != ELIGIBILITY_PROFILE or eligibility.version != ELIGIBILITY_VERSION:
        raise SolveBenchmarkError("unsupported benchmark eligibility projection")
    if eligibility.collection_id != collection.collection_id:
        raise SolveBenchmarkError("benchmark eligibility collection identity does not match")
    if eligibility.collection_inventory_sha256 != collection.inventory_sha256:
        raise SolveBenchmarkError("benchmark eligibility inventory hash does not match collection")


def _required_artifact_bytes(
    entries: Iterable[BenchmarkEligibilityEntry],
    puzzle_artifact_bytes: Mapping[str, bytes],
) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for entry in entries:
        artifact_id = entry.selected_puzzle_artifact_id
        artifact_sha256 = entry.selected_puzzle_artifact_sha256
        byte_length = entry.selected_puzzle_artifact_byte_length
        if artifact_id is None or artifact_sha256 is None or byte_length is None:
            raise SolveBenchmarkError(
                f"eligible puzzle {entry.puzzle_id} has incomplete exact artifact identity"
            )
        payload = puzzle_artifact_bytes.get(artifact_id)
        if not isinstance(payload, bytes):
            raise SolveBenchmarkError(
                f"exact puzzle artifact bytes are missing for {entry.puzzle_id}"
            )
        if len(payload) != byte_length or sha256_bytes(payload) != artifact_sha256:
            raise SolveBenchmarkError(
                f"exact puzzle artifact bytes do not match {entry.puzzle_id}"
            )
        result[entry.puzzle_id] = payload
    return result


def _benchmark_identity(
    *,
    collection: CollectionDefinition,
    eligibility: BenchmarkEligibilityProjection,
    serializer: ModelPuzzleTextSerializer,
    verifier: VerifierIdentity,
    attempt_budget: int,
) -> BenchmarkIdentity:
    manifest_sha256 = sha256_bytes(canonical_json_bytes(collection.manifest))
    return BenchmarkIdentity(
        protocol_version=PROTOCOL_VERSION,
        collection_id=collection.collection_id,
        collection_manifest_sha256=manifest_sha256,
        puzzle_serializer=serializer.format_name,
        puzzle_serializer_version=serializer.version,
        candidate_output_compiler=CANDIDATE_OUTPUT_COMPILER,
        candidate_output_compiler_version=CANDIDATE_OUTPUT_COMPILER_VERSION,
        verifier_implementation=verifier.verifier_implementation,
        verifier_revision=verifier.verifier_revision,
        verifier_sha256=verifier.verifier_sha256,
        validation_profile=verifier.validation_profile,
        attempt_profile=ATTEMPT_PROFILE,
        attempt_budget=attempt_budget,
        scoring_version=SCORING_VERSION,
        executable_inventory_sha256=eligibility.inventory_sha256,
    )


def _run_identity(
    identity: BenchmarkIdentity,
    runner: SolverIdentity,
) -> BenchmarkRunIdentity:
    return BenchmarkRunIdentity(
        benchmark_id=benchmark_id(identity),
        system_id=runner.system_id,
        system_revision=runner.system_revision,
        harness_implementation=HARNESS_IMPLEMENTATION,
        harness_revision=HARNESS_REVISION,
        generation_config_sha256=runner.generation_config_sha256,
    )


def _validate_verification_result(
    result: VerificationResult,
    *,
    verifier: VerifierIdentity,
    puzzle_artifact_id: str,
    solution_id: str,
) -> None:
    expected_id = verification_id(
        puzzle_artifact_id=puzzle_artifact_id,
        solution_id=solution_id,
        verifier_implementation=verifier.verifier_implementation,
        verifier_revision=verifier.verifier_revision,
        verifier_sha256=verifier.verifier_sha256,
        validation_profile=verifier.validation_profile,
    )
    identity = (
        result.verification_id,
        result.puzzle_artifact_id,
        result.solution_id,
        result.verifier_implementation,
        result.verifier_revision,
        result.verifier_sha256,
        result.validation_profile,
    )
    expected = (
        expected_id,
        puzzle_artifact_id,
        solution_id,
        verifier.verifier_implementation,
        verifier.verifier_revision,
        verifier.verifier_sha256,
        verifier.validation_profile,
    )
    if identity != expected:
        raise SolveBenchmarkError("verifier result identity does not match verification input")


def _verification_outcome(result: VerificationResult) -> str:
    if result.parse_status not in {"passed", "failed"}:
        raise SolveBenchmarkError(f"unsupported verifier parse status {result.parse_status!r}")
    if result.simulation_status not in {"passed", "failed", "not_run"}:
        raise SolveBenchmarkError(
            f"unsupported verifier simulation status {result.simulation_status!r}"
        )
    if result.parse_status == "failed":
        return "solution_parse_failed"
    if result.simulation_status == "passed":
        return "success"
    return "simulation_failed"


def _attempt_from_verification(
    *,
    benchmark_id_value: str,
    run_id_value: str,
    puzzle_id: str,
    attempt_index: int,
    candidate_sha256: str,
    output: RunnerOutput,
    result: VerificationResult,
) -> dict[str, Any]:
    outcome = _verification_outcome(result)
    success = outcome == "success"
    return build_attempt_result(
        benchmark_id=benchmark_id_value,
        run_id=run_id_value,
        puzzle_id=puzzle_id,
        attempt_index=attempt_index,
        outcome=outcome,
        candidate_sha256=candidate_sha256,
        verification_id=result.verification_id,
        cost=result.cost if success else None,
        cycles=result.cycles if success else None,
        area=result.area if success else None,
        instructions=result.instructions if success else None,
        error_code=None if success else (result.error_code or outcome),
        model_calls=output.model_calls,
        input_tokens=output.input_tokens,
        output_tokens=output.output_tokens,
        verifier_calls=1,
    )


def run_solve_benchmark(
    *,
    collection: CollectionDefinition,
    eligibility: BenchmarkEligibilityProjection,
    definitions: Iterable[Mapping[str, Any]],
    puzzle_artifact_bytes: Mapping[str, bytes],
    runner: SolveRunner,
    verifier: Verifier,
    attempt_budget: int = 1,
) -> SolveBenchmarkResult:
    if isinstance(attempt_budget, bool) or not isinstance(attempt_budget, int) or attempt_budget < 1:
        raise SolveBenchmarkError("attempt_budget must be a positive integer")

    _validate_projection(collection, eligibility)
    collection_rows = _collection_rows(collection)
    definitions_by_puzzle = _definitions_by_puzzle(definitions)
    executable = tuple(sorted(eligibility.executable_entries, key=lambda row: row.puzzle_id))
    if not executable:
        raise SolveBenchmarkError("benchmark eligibility contains no executable puzzles")

    artifact_bytes = _required_artifact_bytes(executable, puzzle_artifact_bytes)
    for entry in executable:
        definition = definitions_by_puzzle.get(entry.puzzle_id)
        row = collection_rows.get(entry.puzzle_id)
        if definition is None or row is None:
            raise SolveBenchmarkError(f"missing canonical facts for {entry.puzzle_id}")
        if definition["puzzle_definition_id"] != entry.puzzle_definition_id:
            raise SolveBenchmarkError(
                f"puzzle definition identity does not match eligibility for {entry.puzzle_id}"
            )
        if not row.get("game_puzzle_id"):
            raise SolveBenchmarkError(f"collection puzzle {entry.puzzle_id} has no game puzzle id")

    serializer = ModelPuzzleTextSerializer()
    verifier_identity = verifier.identity
    identity = _benchmark_identity(
        collection=collection,
        eligibility=eligibility,
        serializer=serializer,
        verifier=verifier_identity,
        attempt_budget=attempt_budget,
    )
    run = _run_identity(identity, runner.identity)
    benchmark_id_value = benchmark_id(identity)
    run_id_value = benchmark_run_id(run)
    puzzle_results: list[dict[str, Any]] = []

    for entry in executable:
        definition = definitions_by_puzzle[entry.puzzle_id]
        row = collection_rows[entry.puzzle_id]
        puzzle_text = serializer.serialize_puzzle(definition)
        attempts: list[dict[str, Any]] = []

        for attempt_index in range(1, attempt_budget + 1):
            output = runner.generate(
                puzzle_id=entry.puzzle_id,
                puzzle_text=puzzle_text,
                attempt_index=attempt_index,
            )
            try:
                candidate = compile_candidate_output(output.raw_output)
            except CandidateOutputCompileError as exc:
                attempts.append(
                    build_attempt_result(
                        benchmark_id=benchmark_id_value,
                        run_id=run_id_value,
                        puzzle_id=entry.puzzle_id,
                        attempt_index=attempt_index,
                        outcome="output_compile_failed",
                        candidate_sha256=None,
                        verification_id=None,
                        cost=None,
                        cycles=None,
                        area=None,
                        instructions=None,
                        error_code=exc.code,
                        model_calls=output.model_calls,
                        input_tokens=output.input_tokens,
                        output_tokens=output.output_tokens,
                        verifier_calls=0,
                    )
                )
                continue

            try:
                parse_candidate_solution(
                    candidate,
                    expected_puzzle_name=row["game_puzzle_id"],
                )
            except PuzzleSolutionMismatchError as exc:
                attempts.append(
                    build_attempt_result(
                        benchmark_id=benchmark_id_value,
                        run_id=run_id_value,
                        puzzle_id=entry.puzzle_id,
                        attempt_index=attempt_index,
                        outcome="puzzle_solution_mismatch",
                        candidate_sha256=candidate.candidate_sha256,
                        verification_id=None,
                        cost=None,
                        cycles=None,
                        area=None,
                        instructions=None,
                        error_code=exc.code,
                        model_calls=output.model_calls,
                        input_tokens=output.input_tokens,
                        output_tokens=output.output_tokens,
                        verifier_calls=0,
                    )
                )
                continue
            except SolutionParseError:
                attempts.append(
                    build_attempt_result(
                        benchmark_id=benchmark_id_value,
                        run_id=run_id_value,
                        puzzle_id=entry.puzzle_id,
                        attempt_index=attempt_index,
                        outcome="solution_parse_failed",
                        candidate_sha256=candidate.candidate_sha256,
                        verification_id=None,
                        cost=None,
                        cycles=None,
                        area=None,
                        instructions=None,
                        error_code="solution_parse_failed",
                        model_calls=output.model_calls,
                        input_tokens=output.input_tokens,
                        output_tokens=output.output_tokens,
                        verifier_calls=0,
                    )
                )
                continue

            puzzle_artifact_id = entry.selected_puzzle_artifact_id
            if puzzle_artifact_id is None:
                raise SolveBenchmarkError(
                    f"eligible puzzle {entry.puzzle_id} has no selected puzzle artifact"
                )
            solution_id = f"om.solution.sha256.{candidate.candidate_sha256}"
            verification_input = VerificationInput(
                puzzle_artifact_id=puzzle_artifact_id,
                solution_id=solution_id,
                puzzle_bytes=artifact_bytes[entry.puzzle_id],
                solution_bytes=candidate.solution_bytes,
                validation_profile=verifier_identity.validation_profile,
            )
            verification_result = verifier.verify(verification_input)
            _validate_verification_result(
                verification_result,
                verifier=verifier_identity,
                puzzle_artifact_id=puzzle_artifact_id,
                solution_id=solution_id,
            )
            attempt = _attempt_from_verification(
                benchmark_id_value=benchmark_id_value,
                run_id_value=run_id_value,
                puzzle_id=entry.puzzle_id,
                attempt_index=attempt_index,
                candidate_sha256=candidate.candidate_sha256,
                output=output,
                result=verification_result,
            )
            attempts.append(attempt)
            if attempt["outcome"] == "success":
                break

        puzzle_results.append(
            build_puzzle_result(
                benchmark_id=benchmark_id_value,
                run_id=run_id_value,
                puzzle_id=entry.puzzle_id,
                attempts=attempts,
            )
        )

    report = aggregate_benchmark_report(
        identity=identity,
        run=run,
        expected_puzzle_ids=[entry.puzzle_id for entry in executable],
        puzzle_results=puzzle_results,
    )
    return SolveBenchmarkResult(
        eligibility=eligibility,
        puzzle_results=tuple(puzzle_results),
        report=report,
    )