from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Protocol

from .errors import CorpusError
from .hashing import sha256_file
from .verification import (
    VerificationInput,
    VerificationResult,
    VerifierIdentity,
    verification_id,
)

OMSIM_LIBVERIFY_REVISION = "758f4a4b4c9e24f50294801da774a0960c922bab"
OMSIM_LIBVERIFY_PROFILE = "omsim-libverify-v1"
OMSIM_LIBVERIFY_IMPLEMENTATION = "omsim-libverify"
OMSIM_LIBVERIFY_CYCLE_LIMIT = 1_000_000

_METRICS = ("cost", "cycles", "area", "instructions")
_PARSE_ERROR_SOURCES = {"puzzle", "solution"}
_ERROR_CODES = {
    "puzzle": "puzzle_parse_failed",
    "solution": "solution_parse_failed",
    "verifier": "simulation_failed",
}


class LibverifyError(CorpusError):
    """Raised when the pinned libverify contract cannot be used safely."""


class LibverifyBackend(Protocol):
    binary_sha256: str

    def create(self, puzzle_bytes: bytes, solution_bytes: bytes) -> object: ...

    def destroy(self, handle: object) -> None: ...

    def error(self, handle: object) -> str | None: ...

    def error_source(self, handle: object) -> str | None: ...

    def error_cycle(self, handle: object) -> int: ...

    def error_location(self, handle: object) -> tuple[int, int]: ...

    def set_cycle_limit(self, handle: object, cycle_limit: int) -> None: ...

    def evaluate_metric(self, handle: object, name: str) -> int: ...


class CtypesLibverifyBackend:
    """ctypes binding for the small stable surface exported by omsim/libverify."""

    def __init__(self, library: object, *, binary_sha256: str) -> None:
        self._library = library
        self.binary_sha256 = binary_sha256
        self._configure_signatures()

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        expected_sha256: str,
    ) -> CtypesLibverifyBackend:
        path = Path(path)
        actual_sha256 = sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise LibverifyError(
                "libverify binary hash mismatch: "
                f"expected {expected_sha256}, observed {actual_sha256}"
            )
        return cls(ctypes.CDLL(str(path)), binary_sha256=actual_sha256)

    def _configure_signatures(self) -> None:
        library = self._library
        library.verifier_create.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
        ]
        library.verifier_create.restype = ctypes.c_void_p
        library.verifier_destroy.argtypes = [ctypes.c_void_p]
        library.verifier_destroy.restype = None
        library.verifier_error.argtypes = [ctypes.c_void_p]
        library.verifier_error.restype = ctypes.c_char_p
        library.verifier_error_source.argtypes = [ctypes.c_void_p]
        library.verifier_error_source.restype = ctypes.c_char_p
        library.verifier_error_cycle.argtypes = [ctypes.c_void_p]
        library.verifier_error_cycle.restype = ctypes.c_int
        library.verifier_error_location_u.argtypes = [ctypes.c_void_p]
        library.verifier_error_location_u.restype = ctypes.c_int
        library.verifier_error_location_v.argtypes = [ctypes.c_void_p]
        library.verifier_error_location_v.restype = ctypes.c_int
        library.verifier_set_cycle_limit.argtypes = [ctypes.c_void_p, ctypes.c_int]
        library.verifier_set_cycle_limit.restype = None
        library.verifier_evaluate_metric.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.verifier_evaluate_metric.restype = ctypes.c_longlong

    @staticmethod
    def _buffer(value: bytes) -> tuple[object, int]:
        if not value:
            empty = (ctypes.c_ubyte * 1)()
            return empty, 0
        data = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        return data, len(value)

    def create(self, puzzle_bytes: bytes, solution_bytes: bytes) -> object:
        puzzle, puzzle_length = self._buffer(puzzle_bytes)
        solution, solution_length = self._buffer(solution_bytes)
        handle = self._library.verifier_create(
            puzzle,
            puzzle_length,
            solution,
            solution_length,
        )
        if not handle:
            raise LibverifyError("libverify failed to allocate a verifier handle")
        return handle

    def destroy(self, handle: object) -> None:
        self._library.verifier_destroy(handle)

    @staticmethod
    def _decoded(value: bytes | None) -> str | None:
        return value.decode("utf-8", errors="replace") if value else None

    def error(self, handle: object) -> str | None:
        return self._decoded(self._library.verifier_error(handle))

    def error_source(self, handle: object) -> str | None:
        return self._decoded(self._library.verifier_error_source(handle))

    def error_cycle(self, handle: object) -> int:
        return int(self._library.verifier_error_cycle(handle))

    def error_location(self, handle: object) -> tuple[int, int]:
        return (
            int(self._library.verifier_error_location_u(handle)),
            int(self._library.verifier_error_location_v(handle)),
        )

    def set_cycle_limit(self, handle: object, cycle_limit: int) -> None:
        self._library.verifier_set_cycle_limit(handle, cycle_limit)

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

    @property
    def identity(self) -> VerifierIdentity:
        return VerifierIdentity(
            verifier_implementation=OMSIM_LIBVERIFY_IMPLEMENTATION,
            verifier_revision=OMSIM_LIBVERIFY_REVISION,
            verifier_sha256=self._backend.binary_sha256,
            validation_profile=OMSIM_LIBVERIFY_PROFILE,
        )

    @classmethod
    def from_library(
        cls,
        path: Path,
        *,
        expected_sha256: str,
    ) -> LibverifyVerifier:
        return cls(
            CtypesLibverifyBackend.from_path(
                path,
                expected_sha256=expected_sha256,
            )
        )

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
                    parse_failure = source in _PARSE_ERROR_SOURCES
                    return _result(
                        value,
                        self._backend.binary_sha256,
                        parse_status="failed" if parse_failure else "passed",
                        simulation_status="not_run" if parse_failure else "failed",
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