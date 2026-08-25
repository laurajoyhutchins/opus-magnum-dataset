from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _reserve_sibling_path(destination: Path, marker: str) -> Path:
    path = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.{marker}-",
            dir=destination.parent,
        )
    )
    path.rmdir()
    return path


@contextmanager
def publish_directory(destination: Path) -> Iterator[Path]:
    """Populate a sibling candidate and promote it only after the block succeeds."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.candidate-",
            dir=destination.parent,
        )
    )

    try:
        yield candidate

        previous: Path | None = None
        if _path_exists(destination):
            previous = _reserve_sibling_path(destination, "previous")
            destination.replace(previous)

        try:
            candidate.replace(destination)
        except BaseException:
            if previous is not None:
                previous.replace(destination)
                previous = None
            raise

        if previous is not None:
            try:
                _remove_path(previous)
            except OSError:
                # Promotion is already committed. Preserve the backup rather than
                # report a false publication failure after visible state changed.
                pass
    finally:
        if _path_exists(candidate):
            try:
                _remove_path(candidate)
            except OSError:
                # Candidate cleanup must not mask the operation's primary outcome.
                # Preserve residue for diagnosis instead of attempting compensation.
                pass
