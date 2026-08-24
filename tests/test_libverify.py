from __future__ import annotations

import ctypes
import hashlib
from dataclasses import replace

import pytest

from opus_corpus.libverify import (
    OMSIM_LIBVERIFY_PROFILE,
    OMSIM_LIBVERIFY_REVISION,
    CtypesLibverifyBackend,
    LibverifyError,
    LibverifyVerifier,
)
from opus_corpus.verification import VerificationInput, verification_id


class ScriptedBackend:
    binary_sha256 = "a" * 64

    def __init__(
        self,
        *,
        initial_error: tuple[str, str, int, int, int] | None = None,
        metric_error: tuple[str, tuple[str, str, int, int, int]] | None = None,
    ) -> None:
        self.current_error = initial_error
        self.metric_error = metric_error
        self.metric_values = {
            "cost": 42,
            "instructions": 9,
            "cycles": 17,
            "area": 13,
        }
        self.created: list[tuple[bytes, bytes]] = []
        self.cycle_limits: list[int] = []
        self.evaluated_metrics: list[str] = []
        self.destroyed = 0

    def create(self, puzzle_bytes: bytes, solution_bytes: bytes) -> object:
        self.created.append((puzzle_bytes, solution_bytes))
        return object()

    def destroy(self, handle: object) -> None:
        self.destroyed += 1

    def set_cycle_limit(self, handle: object, cycle_limit: int) -> None:
        self.cycle_limits.append(cycle_limit)

    def error(self, handle: object) -> str | None:
        return None if self.current_error is None else self.current_error[1]

    def error_source(self, handle: object) -> str | None:
        return None if self.current_error is None else self.current_error[0]

    def error_cycle(self, handle: object) -> int:
        return 0 if self.current_error is None else self.current_error[2]

    def error_location(self, handle: object) -> tuple[int, int]:
        if self.current_error is None:
            return 0, 0
        return self.current_error[3], self.current_error[4]

    def evaluate_metric(self, handle: object, name: str) -> int:
        self.evaluated_metrics.append(name)
        if self.metric_error is not None and name == self.metric_error[0]:
            self.current_error = self.metric_error[1]
            return -1
        return self.metric_values[name]


class FakeCFunction:
    def __init__(self, return_value: object = None) -> None:
        self.return_value = return_value
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: list[object] | None = None
        self.restype: object = None

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        return self.return_value


class FakeCLibrary:
    def __init__(self, *, error: bytes | None = b"collision") -> None:
        self.verifier_create_from_bytes = FakeCFunction(1234)
        self.verifier_destroy = FakeCFunction()
        self.verifier_set_cycle_limit = FakeCFunction()
        self.verifier_error = FakeCFunction(error)
        self.verifier_error_source = FakeCFunction(b"simulation" if error else None)
        self.verifier_error_cycle = FakeCFunction(7 if error else 0)
        self.verifier_error_location_u = FakeCFunction(-1 if error else 0)
        self.verifier_error_location_v = FakeCFunction(2 if error else 0)
        self.verifier_evaluate_metric = FakeCFunction(11)


def verification_input(profile: str = OMSIM_LIBVERIFY_PROFILE) -> VerificationInput:
    return VerificationInput(
        puzzle_artifact_id="om.puzzle-artifact.sha256." + "1" * 64,
        solution_id="om.solution.sha256." + "2" * 64,
        puzzle_bytes=b"puzzle\x00bytes",
        solution_bytes=b"solution\x00bytes",
        validation_profile=profile,
    )


def test_libverify_recomputes_metrics_and_records_exact_identity():
    backend = ScriptedBackend()
    value = verification_input()

    result = LibverifyVerifier(backend).verify(value)

    expected_id = verification_id(
        puzzle_artifact_id=value.puzzle_artifact_id,
        solution_id=value.solution_id,
        verifier_implementation="omsim-libverify",
        verifier_revision=OMSIM_LIBVERIFY_REVISION,
        verifier_sha256=backend.binary_sha256,
        validation_profile=OMSIM_LIBVERIFY_PROFILE,
    )
    assert result.verification_id == expected_id
    assert result.verifier_implementation == "omsim-libverify"
    assert result.verifier_revision == OMSIM_LIBVERIFY_REVISION
    assert result.verifier_sha256 == backend.binary_sha256
    assert result.validation_profile == OMSIM_LIBVERIFY_PROFILE
    assert result.parse_status == "passed"
    assert result.simulation_status == "passed"
    assert (result.cost, result.instructions, result.cycles, result.area) == (42, 9, 17, 13)
    assert result.vanilla_constructible is None
    assert result.record_eligible is None
    assert result.error_code is None
    assert result.error_detail is None
    assert backend.created == [(value.puzzle_bytes, value.solution_bytes)]
    assert backend.cycle_limits == [150000]
    assert backend.evaluated_metrics == ["cost", "instructions", "cycles", "area"]
    assert backend.destroyed == 1


def test_libverify_rejects_an_unpinned_validation_profile_before_native_execution():
    backend = ScriptedBackend()

    with pytest.raises(LibverifyError, match="unsupported validation profile"):
        LibverifyVerifier(backend).verify(verification_input("ordinary-v1"))

    assert backend.created == []


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        ("puzzle file", "puzzle_parse_failed"),
        ("solution file", "solution_parse_failed"),
    ],
)
def test_libverify_preserves_parse_failures(source: str, expected_code: str):
    backend = ScriptedBackend(initial_error=(source, "invalid bytes", 0, 0, 0))

    result = LibverifyVerifier(backend).verify(verification_input())

    assert result.parse_status == "failed"
    assert result.simulation_status == "not_run"
    assert (result.cost, result.instructions, result.cycles, result.area) == (
        None,
        None,
        None,
        None,
    )
    assert result.error_code == expected_code
    assert result.error_detail == "invalid bytes"
    assert result.vanilla_constructible is None
    assert result.record_eligible is None
    assert backend.evaluated_metrics == []
    assert backend.destroyed == 1


def test_libverify_preserves_structured_simulation_failure_and_discards_partial_metrics():
    backend = ScriptedBackend(
        metric_error=("cycles", ("simulation", "collision", 12, -3, 4))
    )

    result = LibverifyVerifier(backend).verify(verification_input())

    assert result.parse_status == "passed"
    assert result.simulation_status == "failed"
    assert (result.cost, result.instructions, result.cycles, result.area) == (
        None,
        None,
        None,
        None,
    )
    assert result.error_code == "simulation_failed"
    assert result.error_detail == "collision on cycle 12 at -3 4"
    assert backend.evaluated_metrics == ["cost", "instructions", "cycles"]
    assert backend.destroyed == 1


def test_libverify_preserves_metric_evaluation_failure():
    backend = ScriptedBackend(metric_error=("cost", ("metric", "unknown metric", 0, 0, 0)))

    result = LibverifyVerifier(backend).verify(verification_input())

    assert result.parse_status == "passed"
    assert result.simulation_status == "failed"
    assert result.error_code == "metric_evaluation_failed"
    assert result.error_detail == "unknown metric"
    assert backend.destroyed == 1


def test_libverify_repeat_evaluation_is_deterministic():
    backend = ScriptedBackend()
    verifier = LibverifyVerifier(backend)
    value = verification_input()

    first = verifier.verify(value)
    backend.current_error = None
    second = verifier.verify(replace(value))

    assert first == second
    assert backend.destroyed == 2


def test_ctypes_backend_hashes_library_configures_abi_and_preserves_embedded_nuls(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    library_path = tmp_path / "libverify.so"
    library_bytes = b"native-library-fixture"
    library_path.write_bytes(library_bytes)
    fake = FakeCLibrary()
    loaded_paths: list[str] = []

    def load_library(path: str) -> FakeCLibrary:
        loaded_paths.append(path)
        return fake

    monkeypatch.setattr("opus_corpus.libverify.ctypes.CDLL", load_library)

    backend = CtypesLibverifyBackend.from_path(library_path)
    handle = backend.create(b"puzzle\x00tail", b"solution\x00tail")

    assert loaded_paths == [str(library_path)]
    assert backend.binary_sha256 == hashlib.sha256(library_bytes).hexdigest()
    create_args = fake.verifier_create_from_bytes.calls[0]
    assert bytes(create_args[0].raw[: create_args[1]]) == b"puzzle\x00tail"
    assert bytes(create_args[2].raw[: create_args[3]]) == b"solution\x00tail"
    assert handle == 1234

    backend.set_cycle_limit(handle, 150000)
    assert fake.verifier_set_cycle_limit.calls == [(1234, 150000)]
    assert backend.error(handle) == "collision"
    assert backend.error_source(handle) == "simulation"
    assert backend.error_cycle(handle) == 7
    assert backend.error_location(handle) == (-1, 2)
    assert backend.evaluate_metric(handle, "cost") == 11
    assert fake.verifier_evaluate_metric.calls[-1] == (1234, b"cost")
    backend.destroy(handle)
    assert fake.verifier_destroy.calls == [(1234,)]

    assert fake.verifier_create_from_bytes.argtypes == [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    assert fake.verifier_create_from_bytes.restype is ctypes.c_void_p
    assert fake.verifier_error.restype is ctypes.c_char_p
    assert fake.verifier_error_source.restype is ctypes.c_char_p
    assert fake.verifier_evaluate_metric.argtypes == [ctypes.c_void_p, ctypes.c_char_p]
    assert fake.verifier_evaluate_metric.restype is ctypes.c_int


def test_ctypes_backend_reports_missing_required_abi_symbols_as_a_typed_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    library_path = tmp_path / "libverify.so"
    library_path.write_bytes(b"native-library-fixture")
    monkeypatch.setattr("opus_corpus.libverify.ctypes.CDLL", lambda path: object())

    with pytest.raises(LibverifyError, match="ABI"):
        CtypesLibverifyBackend.from_path(library_path)


def test_libverify_factory_loads_ctypes_backend(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_path = tmp_path / "libverify.so"
    library_path.write_bytes(b"native-library-fixture")
    fake = FakeCLibrary(error=None)
    monkeypatch.setattr("opus_corpus.libverify.ctypes.CDLL", lambda path: fake)

    result = LibverifyVerifier.from_library(library_path).verify(verification_input())

    assert result.parse_status == "passed"
    assert result.simulation_status == "passed"
    assert (result.cost, result.instructions, result.cycles, result.area) == (11, 11, 11, 11)
