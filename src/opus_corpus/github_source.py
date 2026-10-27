from __future__ import annotations

import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import CorpusError

# One shared bound for every official pinned GitHub-source adapter. These are
# deliberately generous for source repositories but finite on untrusted input.
MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 50_000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024


class AcquisitionError(CorpusError):
    """Raised when immutable upstream source acquisition fails."""


def iter_tarball_members(fileobj: BinaryIO) -> Iterator[tuple[str, BinaryIO]]:
    """Yield bounded regular archive members in deterministic normalized path order."""

    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as archive:
            normalized: list[tuple[str, tarfile.TarInfo]] = []
            seen: set[str] = set()
            member_count = 0
            total_size = 0
            # Iterate rather than getmembers() so hostile member counts are
            # rejected while parsing headers, before an unbounded list exists.
            for member in archive:
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise AcquisitionError("GitHub source tarball member count limit exceeded")
                if not member.isfile():
                    continue
                if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                    raise AcquisitionError("GitHub source tarball member size limit exceeded")
                total_size += member.size
                if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise AcquisitionError("GitHub source tarball total size limit exceeded")
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
                    # Individual adapter reads are now bounded by member.size.
                    yield path, extracted
    except tarfile.TarError as exc:
        raise AcquisitionError("invalid GitHub source tarball") from exc


def iter_github_tarball_members(
    owner: str,
    repo: str,
    revision: str,
) -> Iterator[tuple[str, BinaryIO]]:
    """Fetch an exact pinned GitHub tarball with finite temporary-disk usage."""

    url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{revision}"
    request = Request(url, headers={"User-Agent": "opus-magnum-corpus/0.1"})
    try:
        with tempfile.TemporaryFile() as payload:
            with urlopen(request, timeout=60) as response:
                # HTTP Content-Length can reject early but cannot attest to the
                # actual response size, so enforce the limit while streaming.
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        declared_size = int(declared)
                    except (TypeError, ValueError) as exc:
                        raise AcquisitionError("GitHub source tarball invalid Content-Length") from exc
                    if declared_size < 0 or declared_size > MAX_COMPRESSED_BYTES:
                        raise AcquisitionError("GitHub source tarball download size limit exceeded")

                total = 0
                while True:
                    # At the limit, read a single extra byte to prove EOF.
                    chunk = response.read(
                        min(DOWNLOAD_CHUNK_BYTES, MAX_COMPRESSED_BYTES - total + 1)
                    )
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_COMPRESSED_BYTES:
                        raise AcquisitionError("GitHub source tarball download size limit exceeded")
                    payload.write(chunk)
            payload.seek(0)
            yield from iter_tarball_members(payload)
    except (HTTPError, URLError, TimeoutError) as exc:
        detail = f"failed to fetch pinned GitHub source {owner}/{repo}@{revision}"
        raise AcquisitionError(detail) from exc
