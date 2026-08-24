from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from opus_corpus.github_source import download_github_tarball, tarball_files
from opus_corpus.hashing import sha256_file
from opus_corpus.libverify import (
    OMSIM_LIBVERIFY_PROFILE,
    OMSIM_LIBVERIFY_REVISION,
    LibverifyVerifier,
)
from opus_corpus.verification import VerificationInput

_SOURCE_FILES = (
    "collision.c",
    "decode.c",
    "parse.c",
    "sim.c",
    "steady-state.c",
    "verifier.c",
)
_FIXTURE_PUZZLE = "test/puzzle/easy/easy-conduit.puzzle"
_FIXTURE_SOLUTION = "test/solution/easy/easy-conduit-easy-conduit-1.solution"


@pytest.mark.upstream
def test_pinned_libverify_builds_and_verifies_real_upstream_fixture(tmp_path: Path):
    compiler = shutil.which("cc")
    assert compiler is not None, "pinned libverify contract requires a C compiler"

    tarball = download_github_tarball("ianh", "omsim", OMSIM_LIBVERIFY_REVISION)
    files = tarball_files(tarball)
    source_root = tmp_path / "omsim"
    source_root.mkdir()
    for path, payload in files.items():
        if "/" not in path and (path.endswith(".c") or path.endswith(".h")):
            (source_root / path).write_bytes(payload)

    library_path = source_root / "libverify.so"
    completed = subprocess.run(
        [
            compiler,
            "-O2",
            "-std=c11",
            "-pedantic",
            "-Wall",
            "-Wno-missing-braces",
            "-g",
            "-shared",
            "-fpic",
            "-o",
            str(library_path),
            *[str(source_root / name) for name in _SOURCE_FILES],
            "-lm",
        ],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    verifier = LibverifyVerifier.from_library(library_path)
    value = VerificationInput(
        puzzle_artifact_id="om.puzzle-artifact.upstream-fixture",
        solution_id="om.solution.upstream-fixture",
        puzzle_bytes=files[_FIXTURE_PUZZLE],
        solution_bytes=files[_FIXTURE_SOLUTION],
        validation_profile=OMSIM_LIBVERIFY_PROFILE,
    )

    first = verifier.verify(value)
    second = verifier.verify(value)

    assert first == second
    assert first.parse_status == "passed"
    assert first.simulation_status == "passed"
    assert first.error_code is None
    assert first.error_detail is None
    assert first.verifier_implementation == "omsim-libverify"
    assert first.verifier_revision == OMSIM_LIBVERIFY_REVISION
    assert first.verifier_sha256 == sha256_file(library_path)
    assert first.validation_profile == OMSIM_LIBVERIFY_PROFILE
    assert first.vanilla_constructible is None
    assert first.record_eligible is None
    assert first.cost is not None and first.cost >= 0
    assert first.instructions is not None and first.instructions >= 0
    assert first.cycles is not None and first.cycles >= 0
    assert first.area is not None and first.area >= 0
