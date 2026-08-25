from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from .content_store import ContentStore
from .errors import CorpusError
from .ingestion import ArtifactRecord
from .normalization import (
    NormalizedSolutionRecord,
    SolutionNormalizationInput,
    SolutionNormalizer,
    normalized_solution_id,
)
from .solution_parser import ParsedSolutionPart, SolutionParseError, parse_solution_bytes


class SolutionNormalizationError(CorpusError):
    """Raised when parsed solution structure cannot satisfy the normalized contract."""


_OPCODE_NAMES = {
    ord("R"): "rotate_cw",
    ord("r"): "rotate_ccw",
    ord("E"): "extend",
    ord("e"): "retract",
    ord("G"): "grab",
    ord("g"): "drop",
    ord("P"): "pivot_cw",
    ord("p"): "pivot_ccw",
    ord("A"): "track_plus",
    ord("a"): "track_minus",
    ord("C"): "repeat",
    ord("X"): "reset",
    ord("B"): "halt",
    ord("O"): "noop",
    ord(" "): "noop",
}


class OpusSolutionNormalizer:
    version = "opus-solution-v1"

    def normalize(self, value: SolutionNormalizationInput) -> NormalizedSolutionRecord:
        try:
            parsed = parse_solution_bytes(value.solution_bytes)
        except SolutionParseError as exc:
            raise SolutionNormalizationError(f"solution parse failed: {exc}") from exc

        parts = [_normalized_part(index, part) for index, part in enumerate(parsed.parts)]
        tracks = [
            _normalized_track(index, part)
            for index, part in enumerate(parsed.parts)
            if part.name == "track"
        ]
        programs = [
            _normalized_program(index, part)
            for index, part in enumerate(parsed.parts)
            if part.instructions
        ]

        part_type_histogram = Counter(part.name for part in parsed.parts)
        opcode_histogram = Counter(
            _opcode_name(instruction.opcode)
            for part in parsed.parts
            for instruction in part.instructions
        )

        return {
            "normalized_solution_id": normalized_solution_id(
                solution_id=value.solution_id,
                puzzle_id=value.puzzle_id,
                normalizer_version=self.version,
            ),
            "solution_id": value.solution_id,
            "puzzle_id": value.puzzle_id,
            "normalizer_version": self.version,
            "parts": parts,
            "tracks": tracks,
            "programs": programs,
            "summaries": {
                "part_count": len(parts),
                "track_count": len(tracks),
                "track_hex_count": sum(len(track["coordinates"]) for track in tracks),
                "program_count": len(programs),
                "instruction_count": sum(
                    len(program["instructions"]) for program in programs
                ),
                "part_type_histogram": dict(sorted(part_type_histogram.items())),
                "opcode_histogram": dict(sorted(opcode_histogram.items())),
            },
        }


def _opcode_name(opcode: int) -> str:
    return _OPCODE_NAMES.get(opcode, f"unknown:0x{opcode:02x}")


def _part_id(index: int) -> str:
    return f"part-{index:04d}"


def _normalized_part(index: int, part: ParsedSolutionPart) -> dict[str, Any]:
    if not part.name:
        raise SolutionNormalizationError(f"part type is empty for {_part_id(index)}")

    parameters: dict[str, Any] = {
        "size": part.size,
        "input_output_index": part.input_output_index,
        "arm_number": part.arm_number,
    }
    if part.conduit_id is not None:
        parameters["conduit_id"] = part.conduit_id
        parameters["conduit_offsets"] = [
            {"x": offset_x, "y": offset_y} for offset_x, offset_y in part.conduit_offsets
        ]

    return {
        "part_id": _part_id(index),
        "type": part.name,
        "x": part.x,
        "y": part.y,
        "rotation": 0 if part.name == "track" else part.rotation % 6,
        "parameters": parameters,
    }


def _normalized_track(index: int, part: ParsedSolutionPart) -> dict[str, Any]:
    if not part.track_offsets:
        raise SolutionNormalizationError(
            f"track {_part_id(index)} must contain at least one coordinate"
        )
    return {
        "track_id": f"track-{index:04d}",
        "coordinates": [
            {"x": part.x + offset_x, "y": part.y + offset_y}
            for offset_x, offset_y in part.track_offsets
        ],
    }


def _normalized_program(index: int, part: ParsedSolutionPart) -> dict[str, Any]:
    for instruction in part.instructions:
        if instruction.cycle < 0:
            raise SolutionNormalizationError(
                f"negative instruction cycle is not representable for {_part_id(index)}: "
                f"{instruction.cycle}"
            )
    instructions = sorted(part.instructions, key=lambda instruction: instruction.cycle)
    return {
        "arm_id": _part_id(index),
        "instructions": [
            {"cycle": instruction.cycle, "opcode": _opcode_name(instruction.opcode)}
            for instruction in instructions
        ],
    }


def normalize_solution_artifacts(
    artifacts: Iterable[ArtifactRecord],
    store: ContentStore,
    normalizer: SolutionNormalizer,
) -> tuple[NormalizedSolutionRecord, ...]:
    """Derive normalized rows directly from canonical exact-byte solution artifacts."""

    rows: list[NormalizedSolutionRecord] = []
    for artifact in sorted(artifacts, key=lambda row: (row.puzzle_id, row.artifact_id)):
        if artifact.artifact_kind != "solution":
            raise SolutionNormalizationError(
                f"cannot normalize non-solution artifact {artifact.artifact_id}"
            )
        if artifact.artifact_format != "solution":
            raise SolutionNormalizationError(
                f"unsupported solution artifact format {artifact.artifact_format!r}"
            )
        expected_id = f"om.solution.sha256.{artifact.sha256}"
        if artifact.artifact_id != expected_id:
            raise SolutionNormalizationError(
                f"solution artifact id does not match exact bytes: {artifact.artifact_id}"
            )

        stored = store.require(artifact.sha256, artifact.byte_length)
        if artifact.object_key != stored.object_key:
            raise SolutionNormalizationError(
                f"solution artifact object key does not match content store: {artifact.artifact_id}"
            )
        try:
            solution_bytes = store.object_path(artifact.sha256).read_bytes()
        except OSError as exc:
            raise SolutionNormalizationError(
                f"cannot read solution artifact bytes: {artifact.artifact_id}"
            ) from exc

        rows.append(
            normalizer.normalize(
                SolutionNormalizationInput(
                    solution_id=artifact.artifact_id,
                    puzzle_id=artifact.puzzle_id,
                    solution_bytes=solution_bytes,
                )
            )
        )
    return tuple(rows)
