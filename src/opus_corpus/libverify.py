from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Protocol

from .errors import CorpusError
from .hashing import sha256_file
from .verification import VerificationInput, VerificationResult, verification_id

OMSIM_LIBVERIFY_REVISION = "758f4a4b4c9e24f50294801da774a0960c922bab"
OMSIM_LIBVERIFY_PROFILE = "omsim-libverify-v1"
OMSIM_LIBVERIFY_IMPLEMENTATION = "omsim-libverify"
OMSIM_LIBVERIFY_CYCLE_LIMIT = 150000

_METRICS = ("cost", "instructions", "cycles", "area")
_ERROR_CODES = {
    "puzzle file": "puzzle_parse_failed",
    "solution file": "solution_parse_failed",
    "simulation": "simulation_failed",
    "metric": "metric_evaluation_failed",
}


class LibverifyError(CorpusError):
    """Raised when libverify cannot be invoked under the pinned contract."""


class LibverifyBackend(Protocol):
    binary_sha256: str

    def create(self, puzzle_bytes: bytes, solution_bytes: bytes) -> object: ...

    def destroy(self, handle: object) -> None: ...

    def set_cycle_limit(self, handle: object, cycle_limit: int) -> None: ...

    def error(self, handle: object) -> str | None: ...

    def error_source(self, handle: object) -> str | None: ...

    def error_cycle(self, handle: object) -> int: ...

    def error_location(self, handle: object) -> tuple[int, int]: ...

    def evaluate_metric(self, handle: object, name: str) -> int: ...


class CtypesLibverifyBackend:
    """Small ctypes boundary over the documented libverify FFI."""

    def __init__(self, library: object, binary_sha256: str) -> None:
        self._library = library
        self.binary_sha256 = binary_sha256
        self._configure_abi()

    @classmethod
    def from_path(cls, path: Path) -> CtypesLibverifyBackend:
        try:
            digest = sha256_file(path)
            library = ctypes.CDLL(str(path))
        except (OSError, ValueError) as exc:
            raise LibverifyError(f"cannot load libverify shared library: {path}") from exc
        return cls(library, digest)

    def _configure_abi(self) -> None:
        create = self._library.verifier_create_from_bytes
        create.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        create.restype = ctypes.c_void_p

        destroy = self._library.verifier_destroy
        destroy.argtypes = [ctypes.c_void_p]
        destroy.restype = None

        set_cycle_limit = self._library.verifier_set_cycle_limit
        set_cycle_limit.argtypes = [ctypes.c_void_p, ctypes.c_int]
        set_cycle_limit.restype = None

        error = self._library.verifier_error
        error.argtypes = [ctypes.c_void_p]
        error.restype = ctypes.c_char_p

        error_source = self._library.verifier_error_source
        error_source.argtypes = [ctypes.c_void_p]
        error_source.restype = ctypes.c_char_p

        error_cycle = self._library.verifier_error_cycle
        error_cycle.argtypes = [ctypes.c_void_p]
        error_cycle.restype = ctypes.c_int

        error_u = self._library.verifier_error_location_u
        error_u.argtypes = [ctypes.c_void_p]
        error_u.restype = ctypes.c_int

        error_v = self._library.verifier_error_location_v
        error_v.argtypes = [ctypes.c_void_p]
        error_v.restype = ctypes.c_int

        evaluate_metric = self._library.verifier_evaluate_metric
        evaluate_metric.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        evaluate_metric.restype = ctypes.c_int

    def create(self, puzzle_bytes: bytes, solution_bytes: bytes) -> object:
        puzzle_buffer = ctypes.create_string_buffer(puzzle_bytes, len(puzzle_bytes) + 1)
        solution_buffer = ctypes.create_string_buffer(solution_bytes, len(solution_bytes) + 1)
        handle = self._library.verifier_create_from_bytes(
            puzzle_buffer,
            len(puzzle_bytes),
            solution_buffer,
            len(solution_bytes),
        )
        if not handle:
            raise LibverifyError("libverify returned a null verifier handle")
        return handle

    def destroy(self, handle: object) -> None:
        self._library.verifier_destroy(handle)

    def set_cycle_limit(self, handle: object, cycle_limit: int) -> None:
        self._library.verifier_set_cycle_limit(handle, cycle_limit)

    @staticmethod
    def _decode(value: bytes | None) -> str | None:
        if value is None:
            return None
        return value.decode("utf-8")

    def error(self, handle: object) -> str | None:
        return self._decode(self._library.verifier_error(handle))

    def error_source(self, handle: object) -> str | None:
        return self._decode(self._library.verifier_error_source(handle))

    def error_cycle(self, handle: object) -> int:
        return int(self._library.verifier_error_cycle(handle))

    def error_location(self, handle: object) -> tuple[int, int]:
        return (
            int(self._library.verifier_error_location_u(handle)),
            int(self._library.verifier_error_location_v(handle)),
        )

    def evaluate_metric(self, handle: object, name: str) -> int:
        return int(self._library.verifier_evaluate_metric(handle, name.encode("utf-8")))


def _error_detail(backend: LibverifyBackend, handle: object, message: str) -> str:
    cycle = backend.error_cycle(handle)
    if cycle == 0:
        return message
    u, v = backend.error_location(handle)
    return f"{message} on cycle {cycle} at {u} {v}"


def _identity(value: VerificationInput, binary_sha256: str) -> dict[str, str | None]:
    return {
        "puzzle_artifact_id": value.puzzle_artifact_id,
        "solution_id": value.solution_id,
        "verifier_implementation": OMSIM_LIBVERIFY_IMPLEMENTATION,
        "verifier_revision": OMSIM_LIBVERIFY_REVISION,
        "verifier_sha256": binary_sha256,
        "validation_profile": value.validation_profile,
    }


def _result(
    value: VerificationInput,
    binary_sha256: str,
    *,
    parse_status: str,
    simulation_status: str,
    cost: int | None = None,
    cycles: int | None = None,
    area: int | None = None,
    instructions: int | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> VerificationResult:
    identity = _identity(value, binary_sha256)
    return VerificationResult(
        verification_id=verification_id(**identity),
        puzzle_artifact_id=value.puzzle_artifact_id,
        solution_id=value.solution_id,
        verifier_implementation=OMSIM_LIBVERIFY_IMPLEMENTATION,
        verifier_revision=OMSIM_LIBVERIFY_REVISION,
        verifier_sha256=binary_sha256,
        validation_profile=value.validation_profile,
        parse_status=parse_status,
        simulation_status=simulation_status,
        cost=cost,
        cycles=cycles,
        area=area,
        instructions=instructions,
        vanilla_constructible=None,
        record_eligible=None,
        error_code=error_code,
        error_detail=error_detail,
    )


class LibverifyVerifier:
    """Pinned omsim/libverify implementation of the canonical Verifier protocol."""

    def __init__(self, backend: LibverifyBackend) -> None:
        self._backend = backend

    @classmethod
    def from_library(cls, path: Path) -> LibverifyVerifier:
        return cls(CtypesLibverifyBackend.from_path(path))

    def verify(self, value: VerificationInput) -> VerificationResult:
        if value.validation_profile != OMSIM_LIBVERIFY_PROFILE:
            raise LibverifyError(
                f"unsupported validation profile {value.validation_profile!r}; "
                f"expected {OMSIM_LIBVERIFY_PROFILE!r}"
            )

        handle = self._backend.create(value.puzzle_bytes, value.solution_bytes)
        try:
            error = self._backend.error(handle)
            if error is not None:
                source = self._backend.error_source(handle)
                return _result(
                    value,
                    self._backend.binary_sha256,
                    parse_status="failed",
                    simulation_status="not_run",
                    error_code=_ERROR_CODES.get(source, "verifier_failed"),
                    error_detail=_error_detail(self._backend, handle, error),
                )

            self._backend.set_cycle_limit(handle, OMSIM_LIBVERIFY_CYCLE_LIMIT)
            metrics: dict[str, int] = {}
            for name in _METRICS:
                metrics[name] = self._backend.evaluate_metric(handle, name)
                error = self._backend.error(handle)
                if error is not None:
                    source = self._backend.error_source(handle)
                    return _result(
                        value,
                        self._backend.binary_sha256,
                        parse_status="passed",
                        simulation_status="failed",
                        error_code=_ERROR_CODES.get(source, "verifier_failed"),
                        error_detail=_error_detail(self._backend, handle, error),
                    )

            return _result(
                value,
                self._backend.binary_sha256,
                parse_status="passed",
                simulation_status="passed",
                cost=metrics["cost"],
                cycles=metrics["cycles"],
                area=metrics["area"],
                instructions=metrics["instructions"],
            )
        finally:
            self._backend.destroy(handle)
