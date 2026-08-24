from __future__ import annotations

from pathlib import Path


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
