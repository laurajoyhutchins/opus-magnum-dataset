from __future__ import annotations

import io
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar
from urllib.request import urlopen

from ..collections import CollectionDefinition
from .base import SourceAdapter

Download = Callable[[str], bytes]


class AdapterFetchError(RuntimeError):
    """Raised when a source adapter cannot materialize its pinned source."""


def _download_url(url: str) -> bytes:
    with urlopen(url, timeout=60) as response:
        return response.read()


@dataclass(frozen=True)
class GitHubSourceAdapter(SourceAdapter):
    """Materialize one pinned GitHub repository snapshot into the local cache."""

    repository: ClassVar[str]
    download: Download = field(default=_download_url, repr=False, compare=False)

    @property
    def archive_url(self) -> str:
        revision = self.pinned_revision
        if revision is None:
            raise AdapterFetchError(f"source adapter {self.source_id!r} has no pinned revision")
        return f"https://codeload.github.com/{self.repository}/tar.gz/{revision}"

    def fetch(self, collection: CollectionDefinition, cache_root: Path) -> Path:
        """Acquire the pinned repository snapshot once and return its materialized root."""
        del collection
        revision = self.pinned_revision
        if revision is None:
            raise AdapterFetchError(f"source adapter {self.source_id!r} has no pinned revision")

        target = cache_root / self.source_id / revision
        if target.is_dir():
            return target

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = self.download(self.archive_url)
            with tempfile.TemporaryDirectory(
                prefix=f".{revision}.",
                dir=target.parent,
            ) as temp_name:
                extraction_root = Path(temp_name) / "extract"
                extraction_root.mkdir()
                with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                    archive.extractall(extraction_root, filter="data")

                roots = list(extraction_root.iterdir())
                if len(roots) != 1 or not roots[0].is_dir():
                    raise AdapterFetchError(
                        f"source adapter {self.source_id!r} archive has an unexpected layout"
                    )
                roots[0].replace(target)
        except AdapterFetchError:
            raise
        except (OSError, tarfile.TarError) as exc:
            raise AdapterFetchError(
                f"source adapter {self.source_id!r} could not fetch pinned revision {revision}"
            ) from exc

        return target
