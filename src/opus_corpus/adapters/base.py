from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ..collections import CollectionDefinition


class AdapterNotImplementedError(RuntimeError):
    """Raised when a source adapter has not implemented acquisition yet."""


@dataclass(frozen=True)
class SourceAdapter:
    """Minimal contract shared by deterministic source acquisition adapters."""

    source_id: ClassVar[str]
    pinned_revision: ClassVar[str | None]

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> None:
        """Acquire pinned source facts into a local cache."""
        raise AdapterNotImplementedError(f"source adapter {self.source_id!r} is not implemented")
