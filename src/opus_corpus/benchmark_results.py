from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from jsonschema import Draft202012Validator

from .errors import CorpusError
from .hashing import canonical_json_bytes, canonical_records_sha256, sha256_bytes
from .schema_resources import load_schema_resource

OUTCOMES = (
    "output_compile_failed",
    "solution_parse_failed",
    "puzzle_solution_mismatch",
    "simulation_failed",
    "success",
)


class BenchmarkResultError(CorpusError):
    pass


@dataclass(frozen=True)
class BenchmarkIdentity:
    protocol_version: str
    collection_id: str
    collection_manifest_sha256: str
    puzzle_serializer: str
    puzzle_serializer_version: str
    output_parser: str
    output_parser_version: str
    verifier_implementation: str
    verifier_revision: str
    verifier_sha256: str | None
    validation_profile: str
    attempt_profile: str
    attempt_budget: int
    scoring_version: str


@dataclass(frozen=True)
class BenchmarkRunIdentity:
    benchmark_id: str
    system_id: str
    system_revision: str
    harness_implementation: str
    harness_revision: str
    generation_config_sha256: str | None


def benchmark_id(identity: BenchmarkIdentity) -> str:
    digest = sha256_bytes(canonical_json_bytes(asdict(identity)))
    return f"om.benchmark.{digest}"


def benchmark_run_id(identity: BenchmarkRunIdentity) -> str:
    digest = sha256_bytes(canonical_json_bytes(asdict(identity)))
    return f"om.benchmark-run.{digest}"


def benchmark_identity_record(identity: BenchmarkIdentity) -> dict[str, Any]:
    record = {
        "record_type": "benchmark_identity",
        "benchmark_id": benchmark_id(identity),
        **asdict(identity),
    }
    _validate_record(record)
    return record


def benchmark_run_identity_record(identity: BenchmarkRunIdentity) -> dict[str, Any]:
    record = {
        "record_type": "benchmark_run_identity",
        "run_id": benchmark_run_id(identity),
        **asdict(identity),
    }
    _validate_record(record)
    return record


def build_attempt_result(
    *,
    benchmark_id: str,
    run_id: str,
    puzzle_id: str,
    attempt_index: int,
    outcome: str,
    candidate_sha256: str,
    verification_id: str | None,
    cost: int | None,
    cycles: int | None,
    area: int | None,
    instructions: int | None,
    error_code: str | None,
    model_calls: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
    verifier_calls: int,
) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise BenchmarkResultError(f"unsupported benchmark outcome: {outcome!r}")

    if outcome == "output_compile_failed":
        if verification_id is not None or verifier_calls != 0:
            raise BenchmarkResultError(
                "output compile failures cannot carry verifier lineage or verifier calls"
            )
    elif verification_id is None or verifier_calls < 1:
        raise BenchmarkResultError(
            "post-compile benchmark outcomes require verifier lineage and a verifier call"
        )

    metrics = (cost, cycles, area, instructions)
    if outcome == "success":
        if any(value is None for value in metrics):
            raise BenchmarkResultError("successful benchmark attempts require all metrics")
        if error_code is not None:
            raise BenchmarkResultError("successful benchmark attempts cannot carry an error code")
    elif any(value is not None for value in metrics):
        raise BenchmarkResultError("failed benchmark attempts cannot carry success metrics")

    record = {
        "record_type": "attempt",
        "benchmark_id": benchmark_id,
        "run_id": run_id,
        "puzzle_id": puzzle_id,
        "attempt_index": attempt_index,
        "outcome": outcome,
        "candidate_sha256": candidate_sha256,
        "verification_id": verification_id,
        "cost": cost,
        "cycles": cycles,
        "area": area,
        "instructions": instructions,
        "error_code": error_code,
        "model_calls": model_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "verifier_calls": verifier_calls,
    }
    _validate_record(record)
    return record


def build_puzzle_result(
    *,
    benchmark_id: str,
    run_id: str,
    puzzle_id: str,
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not attempts:
        raise BenchmarkResultError(f"puzzle {puzzle_id!r} must have at least one attempt")

    normalized_attempts: list[dict[str, Any]] = []
    for value in attempts:
        attempt = dict(value)
        _validate_record(attempt)
        if attempt.get("record_type") != "attempt":
            raise BenchmarkResultError("puzzle results may contain only attempt records")
        if attempt["benchmark_id"] != benchmark_id:
            raise BenchmarkResultError("attempt benchmark identity does not match puzzle result")
        if attempt["run_id"] != run_id:
            raise BenchmarkResultError("attempt run identity does not match puzzle result")
        if attempt["puzzle_id"] != puzzle_id:
            raise BenchmarkResultError("attempt puzzle identity does not match puzzle result")
        normalized_attempts.append(attempt)

    normalized_attempts.sort(key=lambda attempt: attempt["attempt_index"])
    indexes = [attempt["attempt_index"] for attempt in normalized_attempts]
    expected_indexes = list(range(1, len(normalized_attempts) + 1))
    if indexes != expected_indexes:
        raise BenchmarkResultError(
            f"attempt indexes for puzzle {puzzle_id!r} must be contiguous from 1"
        )

    first_success = next(
        (
            attempt["attempt_index"]
            for attempt in normalized_attempts
            if attempt["outcome"] == "success"
        ),
        None,
    )
    record = {
        "record_type": "puzzle_result",
        "benchmark_id": benchmark_id,
        "run_id": run_id,
        "puzzle_id": puzzle_id,
        "attempts": normalized_attempts,
        "solved": first_success is not None,
        "first_success_attempt": first_success,
    }
    _validate_record(record)
    return record


def aggregate_benchmark_report(
    *,
    identity: BenchmarkIdentity,
    run: BenchmarkRunIdentity,
    expected_puzzle_ids: Sequence[str],
    puzzle_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    benchmark_record = benchmark_identity_record(identity)
    expected_benchmark_id = benchmark_record["benchmark_id"]
    if run.benchmark_id != expected_benchmark_id:
        raise BenchmarkResultError("benchmark run identity does not match benchmark identity")

    expected_ids = list(expected_puzzle_ids)
    if not expected_ids:
        raise BenchmarkResultError("aggregate benchmark reports require expected puzzle IDs")
    if any(not isinstance(puzzle_id, str) or not puzzle_id for puzzle_id in expected_ids):
        raise BenchmarkResultError("expected puzzle IDs must be non-empty strings")
    expected_set = set(expected_ids)
    if len(expected_set) != len(expected_ids):
        raise BenchmarkResultError("expected puzzle IDs must not contain duplicates")

    run_record = benchmark_run_identity_record(run)
    expected_run_id = run_record["run_id"]
    if not puzzle_results:
        raise BenchmarkResultError("aggregate benchmark reports require at least one puzzle result")

    normalized_results: list[dict[str, Any]] = []
    seen_puzzles: set[str] = set()
    for value in puzzle_results:
        result = dict(value)
        _validate_record(result)
        if result.get("record_type") != "puzzle_result":
            raise BenchmarkResultError("aggregate reports may contain only puzzle result records")
        if result["benchmark_id"] != expected_benchmark_id:
            raise BenchmarkResultError("puzzle result benchmark identity does not match report")
        if result["run_id"] != expected_run_id:
            raise BenchmarkResultError("puzzle result run identity does not match report")
        if result["puzzle_id"] in seen_puzzles:
            raise BenchmarkResultError(f"duplicate puzzle result: {result['puzzle_id']!r}")
        seen_puzzles.add(result["puzzle_id"])

        rebuilt = build_puzzle_result(
            benchmark_id=expected_benchmark_id,
            run_id=expected_run_id,
            puzzle_id=result["puzzle_id"],
            attempts=result["attempts"],
        )
        if canonical_json_bytes(rebuilt) != canonical_json_bytes(result):
            raise BenchmarkResultError(
                f"puzzle result {result['puzzle_id']!r} contains inconsistent derived state"
            )
        if len(rebuilt["attempts"]) > identity.attempt_budget:
            raise BenchmarkResultError(
                f"puzzle result {result['puzzle_id']!r} exceeds benchmark attempt budget"
            )
        normalized_results.append(rebuilt)

    if seen_puzzles != expected_set:
        missing = sorted(expected_set - seen_puzzles)
        unexpected = sorted(seen_puzzles - expected_set)
        raise BenchmarkResultError(
            "benchmark puzzle coverage does not match collection: "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )

    normalized_results.sort(key=lambda result: result["puzzle_id"])
    attempts = [attempt for result in normalized_results for attempt in result["attempts"]]
    solved_count = sum(1 for result in normalized_results if result["solved"])
    puzzle_count = len(normalized_results)
    outcome_counts = {outcome: 0 for outcome in OUTCOMES}
    for attempt in attempts:
        outcome_counts[attempt["outcome"]] += 1

    report = {
        "record_type": "aggregate_report",
        "benchmark": benchmark_record,
        "run": run_record,
        "puzzle_count": puzzle_count,
        "solved_count": solved_count,
        "unsolved_count": puzzle_count - solved_count,
        "solve_rate_numerator": solved_count,
        "solve_rate_denominator": puzzle_count,
        "attempt_count": len(attempts),
        "outcome_counts": outcome_counts,
        "verifier_calls": sum(attempt["verifier_calls"] for attempt in attempts),
        "model_calls": _complete_sum(attempts, "model_calls"),
        "input_tokens": _complete_sum(attempts, "input_tokens"),
        "output_tokens": _complete_sum(attempts, "output_tokens"),
        "puzzle_results_sha256": canonical_records_sha256(normalized_results),
    }
    _validate_record(report)
    return report


def _complete_sum(records: Sequence[Mapping[str, Any]], field: str) -> int | None:
    values = [record[field] for record in records]
    if any(value is None for value in values):
        return None
    return sum(values)


def _validate_record(record: Mapping[str, Any]) -> None:
    schema = load_schema_resource("benchmark-results.schema.json").schema
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(dict(record)),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if not errors:
        return
    error = errors[0]
    path = ".".join(str(part) for part in error.absolute_path) or "<record>"
    raise BenchmarkResultError(f"invalid benchmark result at {path}: {error.message}")
