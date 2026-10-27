from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .benchmark_candidate import CandidateOutputCompileError, compile_candidate_output
from .content_store import ContentStore
from .errors import CorpusError
from .hashing import canonical_json_bytes, sha256_bytes
from .schema_resources import load_schema_resource
from .solve_benchmark import SolveBenchmarkResult


class RawCandidateReplayError(CorpusError):
    """Raw candidate artifacts cannot be retained or recompiled as claimed."""


def _private_directory(path: Path) -> Path:
    if path.is_symlink():
        raise RawCandidateReplayError("raw benchmark custody must not traverse symlinks")
    path.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise RawCandidateReplayError("raw benchmark custody directory must be private (0700)")
    return path


def _validate_manifest(manifest: dict[str, Any]) -> None:
    schema = load_schema_resource("benchmark-raw-attempts.schema.json").schema
    errors = list(Draft202012Validator(schema).iter_errors(manifest))
    if errors:
        raise RawCandidateReplayError(
            "invalid raw benchmark manifest: " + sorted(error.message for error in errors)[0]
        )


def retain_raw_attempts(result: SolveBenchmarkResult, custody_root: Path) -> Path:
    """Create-only, private, content-addressed raw candidate storage.

    Caller explicitly selects a private local custody root. No response content
    enters GitHub, logs or benchmark aggregate payloads. If a write is
    interrupted, a repeat can re-use immutable objects and manifest bytes.
    """
    root = _private_directory(Path(custody_root))
    run_dir = _private_directory(root / "raw-benchmark-runs")
    benchmark = result.report["benchmark"]
    run = result.report["run"]
    attempt_by_key = {
        (puzzle["puzzle_id"], attempt["attempt_index"]): attempt
        for puzzle in result.puzzle_results
        for attempt in puzzle["attempts"]
    }
    if len(attempt_by_key) != sum(
        len(puzzle["attempts"]) for puzzle in result.puzzle_results
    ):
        raise RawCandidateReplayError("duplicate benchmark attempt identity")
    observed: set[tuple[str, int]] = set()
    content_store = ContentStore(root)
    entries = []
    for raw in result.raw_outputs:
        key = (raw.puzzle_id, raw.attempt_index)
        if key in observed or key not in attempt_by_key:
            raise RawCandidateReplayError("unmatched or duplicated raw candidate identity")
        observed.add(key)
        attempt = attempt_by_key[key]
        if (
            sha256_bytes(raw.exact_utf8) != raw.raw_output_sha256
            or attempt.get("raw_output_sha256") != raw.raw_output_sha256
        ):
            raise RawCandidateReplayError("raw candidate differs from canonical attempt digest")
        stored = content_store.put_bytes(raw.exact_utf8)
        entries.append({
            "puzzle_id": raw.puzzle_id,
            "attempt_index": raw.attempt_index,
            "raw_output_sha256": raw.raw_output_sha256,
            "raw_output_byte_length": stored.byte_length,
            "object_key": stored.object_key,
            "outcome": attempt["outcome"],
            "candidate_sha256": attempt["candidate_sha256"],
            "error_code": attempt["error_code"],
        })
    if observed != set(attempt_by_key):
        raise RawCandidateReplayError("not every benchmark attempt retains raw candidate bytes")

    manifest = {
        "schema": "om.benchmark-raw-attempts/v1",
        "benchmark_id": benchmark["benchmark_id"],
        "run_id": run["run_id"],
        "puzzle_results_sha256": result.report["puzzle_results_sha256"],
        "attempts": sorted(entries, key=lambda row: (row["puzzle_id"], row["attempt_index"])),
    }
    _validate_manifest(manifest)
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    target = run_dir / f"{run['run_id']}.json"
    if target.is_symlink():
        raise RawCandidateReplayError("raw benchmark manifest cannot be a symlink")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=run_dir, prefix=".raw-run-", delete=False
        ) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(manifest_bytes)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.link(temp_path, target, follow_symlinks=False)
        except FileExistsError:
            if target.read_bytes() != manifest_bytes:
                raise RawCandidateReplayError("existing raw run manifest differs") from None
        if target.read_bytes() != manifest_bytes:
            raise RawCandidateReplayError("raw run manifest readback differs")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return target


def replay_raw_attempts(manifest_path: Path, custody_root: Path) -> tuple[dict[str, Any], ...]:
    """Read exact private bytes and replay deterministic candidate compilation.

    Compiler failures and compiled hashes are independently checked. Simulator
    outcomes require the pinned verifier and benchmark inputs to re-evaluate.
    """
    root = Path(custody_root)
    manifest_path = Path(manifest_path)
    if manifest_path.parent != root / "raw-benchmark-runs" or manifest_path.is_symlink():
        raise RawCandidateReplayError("raw benchmark manifest is outside custody directory")
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise RawCandidateReplayError("raw benchmark manifest is unreadable") from exc
    if not isinstance(manifest, dict):
        raise RawCandidateReplayError("raw benchmark manifest must be an object")
    _validate_manifest(manifest)
    if manifest_path.name != manifest["run_id"] + ".json":
        raise RawCandidateReplayError("raw manifest run ID does not match its custody path")
    store = ContentStore(root)
    checked: list[dict[str, Any]] = []
    seen = set()
    for row in manifest["attempts"]:
        key = (row["puzzle_id"], row["attempt_index"])
        if key in seen:
            raise RawCandidateReplayError("duplicate raw attempt on replay")
        seen.add(key)
        stored = store.require(row["raw_output_sha256"], row["raw_output_byte_length"])
        if row["object_key"] != stored.object_key:
            raise RawCandidateReplayError("raw attempt object path does not match SHA-256")
        raw = store.object_path(stored.sha256).read_bytes()
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RawCandidateReplayError("raw candidate cannot decode as UTF-8") from exc
        try:
            candidate = compile_candidate_output(source)
        except CandidateOutputCompileError as error:
            if row["outcome"] != "output_compile_failed" or row["error_code"] != error.code:
                raise RawCandidateReplayError(
                    "compiler failure does not match retained attempt"
                ) from error
        else:
            if (
                row["outcome"] == "output_compile_failed"
                or candidate.candidate_sha256 != row["candidate_sha256"]
            ):
                raise RawCandidateReplayError(
                    "compiled candidate hash does not match retained attempt"
                )
        checked.append(dict(row))
    return tuple(checked)
