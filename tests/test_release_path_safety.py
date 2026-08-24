from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.errors import ReleaseValidationError
from opus_corpus.release import ConfigRelease, ReleaseManifest, validate_release
from opus_corpus.release_inputs import SCHEMA_FILES
from opus_corpus.schema_resources import load_schema_resource


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture-collection",
        inventory_sha256="a" * 64,
        puzzle_count=0,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "inventory.csv",
        inventory_rows=(),
        manifest={},
    )


def _manifest(parquet_path: str) -> ReleaseManifest:
    configs: dict[str, ConfigRelease] = {}
    for name in ("puzzles", "solutions", "observations", "normalized"):
        schema_resource = load_schema_resource(SCHEMA_FILES[name])
        configs[name] = ConfigRelease(
            schema_path=schema_resource.logical_path,
            schema_sha256=schema_resource.sha256,
            records_sha256="b" * 64,
            row_count=0,
            parquet_path=(
                parquet_path
                if name == "puzzles"
                else f"data/{name}/split-00000-of-00001.parquet"
            ),
            parquet_sha256="a" * 64,
            source_path=f"fixtures/{name}.jsonl",
            source_sha256="c" * 64,
        )
    return ReleaseManifest(
        format_version=2,
        corpus_schema_version="0.1",
        collection_id="fixture-collection",
        collection_inventory_sha256="a" * 64,
        split="fixture_collection",
        build_software_revision=None,
        build_config_sha256="a" * 64,
        payload_policy="metadata-only",
        coverage_policy="subset",
        release_metadata={"coverage": {}},
        release_metadata_sha256="d" * 64,
        configs=configs,
        logical_release_sha256="",
    ).with_logical_hash()


def test_validate_release_rejects_symlink_escape_before_parquet_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    output = tmp_path / "release"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (outside / "escape.parquet").write_bytes(b"outside")
    (output / "data").symlink_to(outside, target_is_directory=True)

    release = _manifest("data/escape.parquet")
    monkeypatch.setattr("opus_corpus.release._read_manifest", lambda *_: release)
    monkeypatch.setattr("opus_corpus.release.sha256_file", lambda *_: "a" * 64)

    def fail_read(*_args, **_kwargs):
        raise AssertionError("unsafe manifest path reached Parquet reader")

    monkeypatch.setattr("opus_corpus.release.read_parquet", fail_read)
    cfg = SimpleNamespace(path=tmp_path / "corpus.toml")

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(_collection(tmp_path), output, cfg)

    assert "release_manifest_path_unsafe" in {error.code for error in exc.value.errors}
