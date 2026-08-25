from __future__ import annotations

import importlib
import struct
from pathlib import Path
from typing import Any

import pytest

from opus_corpus.content_store import ContentStore
from opus_corpus.ingestion import ArtifactRecord
from opus_corpus.normalization import SolutionNormalizationInput, normalized_solution_id
from opus_corpus.schema_resources import load_schema_resource


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _i32(value: int) -> bytes:
    return struct.pack("<i", value)


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            encoded.append(byte | 0x80)
        else:
            encoded.append(byte)
            return bytes(encoded)


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return _varint(len(encoded)) + encoded


def _part(
    name: str,
    *,
    x: int,
    y: int,
    size: int = 1,
    rotation: int = 0,
    input_output_index: int = 0,
    instructions: tuple[tuple[int, int], ...] = (),
    track_offsets: tuple[tuple[int, int], ...] = (),
    arm_number: int = 0,
    conduit_id: int | None = None,
    conduit_offsets: tuple[tuple[int, int], ...] = (),
) -> bytes:
    body = bytearray()
    body += _string(name)
    body += b"\x01"
    body += _i32(x)
    body += _i32(y)
    body += _u32(size)
    body += _i32(rotation)
    body += _u32(input_output_index)
    body += _u32(len(instructions))
    for cycle, opcode in instructions:
        body += _i32(cycle)
        body += bytes([opcode])
    if name == "track":
        body += _u32(len(track_offsets))
        for offset_x, offset_y in track_offsets:
            body += _i32(offset_x)
            body += _i32(offset_y)
    body += _u32(arm_number)
    if name == "pipe":
        assert conduit_id is not None
        body += _u32(conduit_id)
        body += _u32(len(conduit_offsets))
        for offset_x, offset_y in conduit_offsets:
            body += _i32(offset_x)
            body += _i32(offset_y)
    return bytes(body)


def solution_bytes(
    *,
    puzzle_name: str = "P001",
    solution_name: str = "fixture",
    solved: bool = True,
    parts: tuple[bytes, ...] | None = None,
) -> bytes:
    if parts is None:
        parts = (
            _part(
                "arm1",
                x=1,
                y=-2,
                size=2,
                rotation=-1,
                arm_number=3,
                instructions=((2, ord("G")), (0, ord("R")), (4, 0xFF)),
            ),
            _part(
                "track",
                x=10,
                y=20,
                track_offsets=((0, 0), (1, 0), (1, 1)),
            ),
        )

    body = bytearray()
    body += _u32(7)
    body += _string(puzzle_name)
    body += _string(solution_name)
    body += _u32(4 if solved else 0)
    if solved:
        for tag, value in enumerate((12, 34, 56, 78)):
            body += _u32(tag)
            body += _u32(value)
    body += _u32(len(parts))
    for part in parts:
        body += part
    return bytes(body)


def parser_module() -> Any:
    return importlib.import_module("opus_corpus.solution_parser")


def normalizer_module() -> Any:
    return importlib.import_module("opus_corpus.solution_normalizer")


def schema_validator() -> Any:
    jsonschema = importlib.import_module("jsonschema")
    schema = load_schema_resource("normalized.schema.json").schema
    return jsonschema.Draft202012Validator(schema)


def test_solution_parser_reads_format_7_structure_and_declared_metrics():
    parser = parser_module()
    parsed = parser.parse_solution_bytes(solution_bytes())

    assert parsed.format_version == 7
    assert parsed.puzzle_name == "P001"
    assert parsed.solution_name == "fixture"
    assert parsed.declared_metrics == {
        "cycles": 12,
        "cost": 34,
        "area": 56,
        "instructions": 78,
    }
    assert len(parsed.parts) == 2

    arm = parsed.parts[0]
    assert (arm.name, arm.x, arm.y, arm.size, arm.rotation, arm.arm_number) == (
        "arm1",
        1,
        -2,
        2,
        -1,
        3,
    )
    assert [(item.cycle, item.opcode) for item in arm.instructions] == [
        (2, ord("G")),
        (0, ord("R")),
        (4, 0xFF),
    ]

    track = parsed.parts[1]
    assert track.track_offsets == ((0, 0), (1, 0), (1, 1))


def test_solution_parser_rejects_unsupported_truncated_and_trailing_data():
    parser = parser_module()
    payload = solution_bytes()

    with pytest.raises(parser.SolutionParseError, match="format version"):
        parser.parse_solution_bytes(_u32(6) + payload[4:])
    with pytest.raises(parser.SolutionParseError, match="truncated"):
        parser.parse_solution_bytes(payload[:-1])
    with pytest.raises(parser.SolutionParseError, match="trailing"):
        parser.parse_solution_bytes(payload + b"x")


def test_solution_parser_rejects_noncanonical_varint_and_invalid_utf8():
    parser = parser_module()
    payload = solution_bytes()

    # The first string starts at byte 4. Encode length 4 non-canonically as 0x84 0x00.
    noncanonical = payload[:4] + b"\x84\x00" + payload[5:]
    with pytest.raises(parser.SolutionParseError, match="varint"):
        parser.parse_solution_bytes(noncanonical)

    invalid_utf8 = payload[:5] + b"\xff" + payload[6:]
    with pytest.raises(parser.SolutionParseError, match="UTF-8"):
        parser.parse_solution_bytes(invalid_utf8)


def test_opus_solution_normalizer_projects_existing_schema_without_declared_scores():
    module = normalizer_module()
    normalizer = module.OpusSolutionNormalizer()
    value = SolutionNormalizationInput(
        solution_id="om.solution.sha256." + "a" * 64,
        puzzle_id="om.puzzle.0001",
        solution_bytes=solution_bytes(),
    )

    record = normalizer.normalize(value)
    schema_validator().validate(record)

    assert record["normalized_solution_id"] == normalized_solution_id(
        solution_id=value.solution_id,
        puzzle_id=value.puzzle_id,
        normalizer_version=normalizer.version,
    )
    assert record["solution_id"] == value.solution_id
    assert record["puzzle_id"] == value.puzzle_id
    assert record["normalizer_version"] == normalizer.version

    assert record["parts"] == [
        {
            "part_id": "part-0000",
            "type": "arm1",
            "x": 1,
            "y": -2,
            "rotation": 5,
            "parameters": {
                "size": 2,
                "input_output_index": 0,
                "arm_number": 3,
            },
        },
        {
            "part_id": "part-0001",
            "type": "track",
            "x": 10,
            "y": 20,
            "rotation": 0,
            "parameters": {
                "size": 1,
                "input_output_index": 0,
                "arm_number": 0,
            },
        },
    ]
    assert record["tracks"] == [
        {
            "track_id": "track-0001",
            "coordinates": [
                {"x": 10, "y": 20},
                {"x": 11, "y": 20},
                {"x": 11, "y": 21},
            ],
        }
    ]
    assert record["programs"] == [
        {
            "arm_id": "part-0000",
            "instructions": [
                {"cycle": 0, "opcode": "rotate_cw"},
                {"cycle": 2, "opcode": "grab"},
                {"cycle": 4, "opcode": "unknown:0xff"},
            ],
        }
    ]
    assert record["summaries"] == {
        "part_count": 2,
        "track_count": 1,
        "track_hex_count": 3,
        "program_count": 1,
        "instruction_count": 3,
        "part_type_histogram": {"arm1": 1, "track": 1},
        "opcode_histogram": {"grab": 1, "rotate_cw": 1, "unknown:0xff": 1},
    }

    # Header metrics are source-declared historical data, never verification truth.
    for metric in ("cost", "cycles", "area", "instructions", "declared_metrics"):
        assert metric not in record


def test_opus_solution_normalizer_is_deterministic():
    module = normalizer_module()
    normalizer = module.OpusSolutionNormalizer()
    value = SolutionNormalizationInput(
        solution_id="om.solution.sha256." + "b" * 64,
        puzzle_id="om.puzzle.0002",
        solution_bytes=solution_bytes(solution_name="deterministic"),
    )

    assert normalizer.normalize(value) == normalizer.normalize(value)


def test_normalization_failure_is_separate_from_solution_parsing():
    parser = parser_module()
    module = normalizer_module()
    payload = solution_bytes(
        parts=(
            _part("arm1", x=0, y=0, instructions=((-1, ord("G")),)),
        )
    )
    parsed = parser.parse_solution_bytes(payload)
    assert parsed.parts[0].instructions[0].cycle == -1

    normalizer = module.OpusSolutionNormalizer()
    with pytest.raises(module.SolutionNormalizationError, match="negative instruction cycle"):
        normalizer.normalize(
            SolutionNormalizationInput(
                solution_id="om.solution.sha256." + "c" * 64,
                puzzle_id="om.puzzle.0003",
                solution_bytes=payload,
            )
        )


def _artifact(store: ContentStore, puzzle_id: str, payload: bytes) -> ArtifactRecord:
    stored = store.put_bytes(payload)
    return ArtifactRecord(
        artifact_kind="solution",
        artifact_id=f"om.solution.sha256.{stored.sha256}",
        puzzle_id=puzzle_id,
        sha256=stored.sha256,
        byte_length=stored.byte_length,
        artifact_format="solution",
        rights_status="unknown",
        object_key=stored.object_key,
    )


def test_normalize_solution_artifacts_consumes_canonical_artifacts_from_content_store(
    tmp_path: Path,
):
    module = normalizer_module()
    store = ContentStore(tmp_path)
    later = _artifact(store, "om.puzzle.0002", solution_bytes(solution_name="later"))
    earlier = _artifact(store, "om.puzzle.0001", solution_bytes(solution_name="earlier"))

    rows = module.normalize_solution_artifacts(
        (later, earlier),
        store,
        module.OpusSolutionNormalizer(),
    )

    assert [row["puzzle_id"] for row in rows] == ["om.puzzle.0001", "om.puzzle.0002"]
    assert [row["solution_id"] for row in rows] == [earlier.artifact_id, later.artifact_id]
