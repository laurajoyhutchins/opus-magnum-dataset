from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class ValidationError:
    code: str
    detail: str
    path: str | None = None
    row: int | None = None

    def render(self) -> str:
        location = self.path or "<input>"
        if self.row is not None:
            location = f"{location}:{self.row}"
        return f"{location}: {self.code}: {self.detail}"


class CorpusError(Exception):
    """Base class for expected corpus-tool errors."""


class ConfigurationError(CorpusError):
    pass


class ValidationFailure(CorpusError):
    def __init__(self, errors: list[ValidationError]):
        self.errors = sorted(errors, key=lambda e: (e.path or "", e.row or -1, e.code, e.detail))
        super().__init__("\n".join(error.render() for error in self.errors))


class CollectionValidationError(ValidationFailure):
    pass


class ReleaseValidationError(ValidationFailure):
    pass


class PayloadPolicyError(ReleaseValidationError):
    pass


class PublicationError(CorpusError):
    pass
