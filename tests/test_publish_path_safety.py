from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.config import CorpusConfig
from opus_corpus.errors import PublicationError
from opus_corpus.publish import stage_release
from opus_corpus.release import ConfigRelease, ReleaseManifest


def _manifest(parquet_path: str) -> ReleaseManifest:
    configs = {
        name: ConfigRelease(
            schema_path=f"schemas/{name}.schema.json",
            schema_sha256="a" * 64,
            records_sha256="b" * 64,
            row_count=1,
            parquet_path=(
                parquet_path
                if name == "puzzles"
                else f"data/{name}/split-00000-of-00001.parquet"
            ),
            parquet_sha256="c" * 64,
            source_path=f"fixtures/{name}.jsonl",
            source_sha256="d" * 64,
        )
        for name in ("puzzles", "solutions", "observations", "normalized")
    }
    return ReleaseManifest(
        2,
        "0.1",
        "fixture-collection",
        "e" * 64,
        "fixture_collection",
        None,
        "f" * 64,
        "metadata-only",
        "subset",
        {"coverage": {}, "known_limitations": []},
        "0" * 64,
        configs,
        "1" * 64,
    )


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        "fixture-collection",
        "e" * 64,
        0,
        tmp_path / "collection.toml",
        tmp_path / "inventory.csv",
        (),
        {},
    )


def _config(tmp_path: Path) -> CorpusConfig:
    path = tmp_path / "corpus.toml"
    path.write_text("x", encoding="utf-8")
    return CorpusConfig(
        tmp_path,
        path,
        1,
        tmp_path / ".release",
        ("puzzles", "solutions", "observations", "normalized"),
        "zstd",
        True,
        True,
        "metadata-only",
        "CHANGE_ME",
        False,
        {"title": "Opus Magnum Corpus", "purpose": "Benchmarking."},
    )


def test_stage_release_rejects_manifest_traversal_before_copying_outside_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = _manifest("../escape.parquet")
    output = tmp_path / "source" / "release"
    destination = tmp_path / "stage" / "dataset"
    output.mkdir(parents=True)
    (output / "release-manifest.json").write_text("{}", encoding="utf-8")
    (output.parent / "escape.parquet").write_bytes(b"outside source")
    for name, entry in release.configs.items():
        if name == "puzzles":
            continue
        path = output / entry.parquet_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"parquet")

    monkeypatch.setattr("opus_corpus.publish.validate_release", lambda *_: release)

    with pytest.raises(PublicationError, match="manifest path"):
        stage_release(_collection(tmp_path), output, destination, _config(tmp_path))

    assert not (destination.parent / "escape.parquet").exists()
