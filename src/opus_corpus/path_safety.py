from __future__ import annotations

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
