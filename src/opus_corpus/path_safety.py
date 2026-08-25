from __future__ import annotations

import stat
from pathlib import Path, PurePosixPath, PureWindowsPath


def resolve_disjoint_trees(source: Path, destination: Path) -> tuple[Path, Path]:
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError(
            f"source and destination paths overlap: {source} and {destination}"
        )
    return source, destination


def resolve_confined_path(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str):
        raise ValueError(f"manifest path must be a string: {relative_path!r}")

    manifest_path = PurePosixPath(relative_path)
    windows_path = PureWindowsPath(relative_path)
    if (
        not relative_path
        or "\\" in relative_path
        or manifest_path.is_absolute()
        or windows_path.drive
    ):
        raise ValueError(f"manifest path must be a relative POSIX path: {relative_path!r}")
    if manifest_path.as_posix() != relative_path or ".." in manifest_path.parts:
        raise ValueError(f"manifest path must be normalized: {relative_path!r}")

    root = Path(root).resolve()
    resolved = (root / Path(*manifest_path.parts)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"manifest path escapes root: {relative_path!r}") from exc
    return resolved


def require_directory_chain(root: Path, directory: Path, *, create: bool) -> bool:
    """Validate canonical directory parents without following descendant symlinks.

    Returns ``False`` when a required component is missing and ``create`` is false.
    Existing descendants must all be real directories. When ``create`` is true,
    missing descendants are created one component at a time and revalidated.
    """

    root = Path(root).absolute()
    directory = Path(directory).absolute()
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"directory escapes root: {directory}") from exc

    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"cannot create root directory: {root}") from exc

    current = root
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not create:
                return False
            try:
                current.mkdir()
            except FileExistsError:
                pass
            except OSError as exc:
                raise ValueError(f"cannot create directory component: {current}") from exc
            try:
                info = current.lstat()
            except OSError as exc:
                raise ValueError(f"cannot validate directory component: {current}") from exc
        except OSError as exc:
            raise ValueError(f"cannot validate directory component: {current}") from exc

        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"unsafe directory component: {current}")

    return True
