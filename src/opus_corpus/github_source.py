from __future__ import annotations

import shutil
import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import CorpusError


class AcquisitionError(CorpusError):
    """Raised when immutable upstream source acquisition fails."""


def iter_tarball_members(fileobj: BinaryIO) -> Iterator[tuple[str, BinaryIO]]:
    """Yield regular archive members in deterministic normalized path order."""

    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as archive:
            normalized: list[tuple[str, tarfile.TarInfo]] = []
            seen: set[str] = set()
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                parts = PurePosixPath(member.name).parts
                if len(parts) < 2:
                    continue
                path = PurePosixPath(*parts[1:]).as_posix()
                if path in seen:
                    raise AcquisitionError(
                        f"duplicate tarball member after root stripping: {path}"
                    )
                seen.add(path)
                normalized.append((path, member))

            for path, member in sorted(normalized, key=lambda item: item[0]):
                extracted = archive.extractfile(member)
                if extracted is not None:
                    yield path, extracted
    except tarfile.TarError as exc:
        raise AcquisitionError("invalid GitHub source tarball") from exc


def iter_github_tarball_members(
    owner: str,
    repo: str,
    revision: str,
) -> Iterator[tuple[str, BinaryIO]]:
    """Fetch a pinned GitHub tarball without buffering the archive in memory."""

    url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{revision}"
    request = Request(url, headers={"User-Agent": "opus-magnum-corpus/0.1"})
    try:
        with tempfile.TemporaryFile() as payload:
            with urlopen(request, timeout=60) as response:
                shutil.copyfileobj(response, payload, length=1024 * 1024)
            payload.seek(0)
            yield from iter_tarball_members(payload)
    except (HTTPError, URLError, TimeoutError) as exc:
        detail = f"failed to fetch pinned GitHub source {owner}/{repo}@{revision}"
        raise AcquisitionError(detail) from exc
