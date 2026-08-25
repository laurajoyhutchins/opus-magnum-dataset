from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.config import load_config
from opus_corpus.errors import ConfigurationError


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("marker", "replacement"),
    [
        ("[corpus]\n", 'unexpected = "value"\n[corpus]\n'),
        ("[corpus]\n", '[corpus]\nunexpected = "value"\n'),
    ],
)
def test_load_config_rejects_unknown_structural_fields(
    tmp_path: Path,
    marker: str,
    replacement: str,
) -> None:
    source = (_repo_root() / "corpus.toml").read_text(encoding="utf-8")
    path = tmp_path / "corpus.toml"
    path.write_text(source.replace(marker, replacement, 1), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unexpected"):
        load_config(path)
