from __future__ import annotations

import io
import tarfile
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import CorpusError


class AcquisitionError(CorpusError):
    """Raised when immutable upstream source acquisition fails."""


def download_github_tarball(owner: str, repo: str, revision: str) -> bytes:
    url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{revision}"
    request = Request(url, headers={"User-Agent": "opus-magnum-corpus/0.1"})
    try:
        with urlopen(request, timeout=60) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        detail = f"failed to fetch pinned GitHub source {owner}/{repo}@{revision}"
        raise AcquisitionError(detail) from exc


def tarball_files(payload: bytes, *, suffix: str | None = None) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                parts = PurePosixPath(member.name).parts
                if len(parts) < 2:
                    continue
                path = PurePosixPath(*parts[1:]).as_posix()
                if suffix is not None and not path.endswith(suffix):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                if path in files:
                    raise AcquisitionError(f"duplicate tarball member after root stripping: {path}")
                files[path] = extracted.read()
    except tarfile.TarError as exc:
        raise AcquisitionError("invalid GitHub source tarball") from exc
    return dict(sorted(files.items()))
