from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from .errors import CorpusError
from .hashing import sha256_bytes
from .solution_parser import ParsedSolution, parse_solution_bytes

CANDIDATE_OUTPUT_COMPILER = "json-base64-solution"
CANDIDATE_OUTPUT_COMPILER_VERSION = "1"
CANDIDATE_OUTPUT_FORMAT = "om-solution-base64-v1"


class CandidateOutputCompileError(CorpusError):
    """Raised when raw benchmark output does not satisfy the v1 output envelope."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PuzzleSolutionMismatchError(CorpusError):
    """Raised when parsed solution identity does not match the benchmark puzzle."""

    code = "puzzle_solution_mismatch"

    def __init__(self, *, expected_puzzle_name: str, observed_puzzle_name: str):
        super().__init__(
            "solution puzzle identity mismatch: "
            f"expected {expected_puzzle_name!r}, observed {observed_puzzle_name!r}"
        )
        self.expected_puzzle_name = expected_puzzle_name
        self.observed_puzzle_name = observed_puzzle_name


@dataclass(frozen=True, slots=True)
class CompiledCandidate:
    solution_bytes: bytes
    candidate_sha256: str


def _object_without_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CandidateOutputCompileError(
                "duplicate_field",
                f"candidate output contains duplicate JSON field {key!r}",
            )
        value[key] = item
    return value


def _parse_envelope(raw_output: str) -> dict[str, Any]:
    if not isinstance(raw_output, str):
        raise CandidateOutputCompileError("not_json", "candidate output must be JSON text")

    text = raw_output.lstrip()
    decoder = json.JSONDecoder(object_pairs_hook=_object_without_duplicate_fields)
    try:
        value, end = decoder.raw_decode(text)
    except CandidateOutputCompileError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CandidateOutputCompileError(
            "not_json",
            "candidate output must contain exactly one JSON value",
        ) from exc

    if text[end:].strip():
        raise CandidateOutputCompileError(
            "trailing_material",
            "candidate output contains material after the JSON envelope",
        )
    if not isinstance(value, dict):
        raise CandidateOutputCompileError(
            "invalid_envelope",
            "candidate output JSON must be an object",
        )
    if set(value) != {"format", "solution_base64"}:
        raise CandidateOutputCompileError(
            "invalid_envelope",
            "candidate output must contain exactly format and solution_base64",
        )
    if not isinstance(value["format"], str) or not isinstance(value["solution_base64"], str):
        raise CandidateOutputCompileError(
            "invalid_envelope",
            "candidate output envelope fields must be strings",
        )
    return value


def _decode_solution_base64(value: str) -> bytes:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise CandidateOutputCompileError(
            "invalid_base64",
            "solution_base64 must contain ASCII base64 text",
        ) from exc

    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as strict_exc:
        try:
            loose_payload = base64.b64decode(encoded, validate=False)
        except (binascii.Error, ValueError):
            raise CandidateOutputCompileError(
                "invalid_base64",
                "solution_base64 is not valid base64",
            ) from strict_exc
        canonical = base64.b64encode(loose_payload)
        if loose_payload and canonical != encoded:
            raise CandidateOutputCompileError(
                "noncanonical_base64",
                "solution_base64 is decodable but not canonically encoded",
            ) from strict_exc
        raise CandidateOutputCompileError(
            "invalid_base64",
            "solution_base64 is not valid base64",
        ) from strict_exc

    if base64.b64encode(payload) != encoded:
        raise CandidateOutputCompileError(
            "noncanonical_base64",
            "solution_base64 is decodable but not canonically encoded",
        )
    if not payload:
        raise CandidateOutputCompileError(
            "empty_candidate",
            "solution_base64 must decode to non-empty solution bytes",
        )
    return payload


def compile_candidate_output(raw_output: str) -> CompiledCandidate:
    """Compile one strict v1 raw model response into exact candidate solution bytes."""

    envelope = _parse_envelope(raw_output)
    if envelope["format"] != CANDIDATE_OUTPUT_FORMAT:
        raise CandidateOutputCompileError(
            "unsupported_format",
            f"unsupported candidate output format {envelope['format']!r}",
        )

    solution_bytes = _decode_solution_base64(envelope["solution_base64"])
    return CompiledCandidate(
        solution_bytes=solution_bytes,
        candidate_sha256=sha256_bytes(solution_bytes),
    )


def parse_candidate_solution(
    candidate: CompiledCandidate,
    *,
    expected_puzzle_name: str,
) -> ParsedSolution:
    """Parse compiled bytes and enforce the solution's exposed puzzle binding."""

    parsed = parse_solution_bytes(candidate.solution_bytes)
    if parsed.puzzle_name != expected_puzzle_name:
        raise PuzzleSolutionMismatchError(
            expected_puzzle_name=expected_puzzle_name,
            observed_puzzle_name=parsed.puzzle_name,
        )
    return parsed