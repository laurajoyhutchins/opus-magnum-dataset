from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.config import CorpusConfig
from opus_corpus.errors import PublicationError
from opus_corpus.publish import publish_release, stage_release
from opus_corpus.release import ConfigRelease, ReleaseManifest


def manifest(coverage_policy: str = "complete") -> ReleaseManifest:
    configs = {
        name: ConfigRelease(
            schema_path=f"schemas/{name}.schema.json",
            schema_sha256="a" * 64,
            records_sha256="b" * 64,
            row_count=1,
            parquet_path=f"data/{name}/base_game_2026_06_16-00000-of-00001.parquet",
            parquet_sha256="c" * 64,
            source_path=f"fixtures/{name}.jsonl",
            source_sha256="d" * 64,
        )
        for name in ("puzzles", "solutions", "observations", "normalized")
    }
    return ReleaseManifest(
        2,
        "0.1",
        "base-game-2026-06-16",
        "e" * 64,
        "base_game_2026_06_16",
        None,
        "f" * 64,
        "metadata-only",
        coverage_policy,
        {"coverage": {}, "known_limitations": []},
        "0" * 64,
        configs,
        "1" * 64,
    )


def collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        "base-game-2026-06-16",
        "e" * 64,
        166,
        tmp_path / "c.toml",
        tmp_path / "c.csv",
        (),
        {},
    )


def config(tmp_path: Path, repo_id: str = "CHANGE_ME") -> CorpusConfig:
    cfg = tmp_path / "corpus.toml"
    cfg.write_text("x", encoding="utf-8")
    return CorpusConfig(
        tmp_path,
        cfg,
        1,
        tmp_path / ".release",
        ("puzzles", "solutions", "observations", "normalized"),
        "zstd",
        True,
        True,
        "metadata-only",
        repo_id,
        False,
        {"title": "Opus Magnum Corpus", "purpose": "Benchmarking."},
    )


def test_stage_contains_only_projection_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = manifest("subset")
    output = tmp_path / "out"
    output.mkdir()
    (output / "release-manifest.json").write_text("{}", encoding="utf-8")
    for entry in release.configs.values():
        path = output / entry.parquet_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"parquet")
    (output / "secret.txt").write_text("do not stage", encoding="utf-8")
    monkeypatch.setattr("opus_corpus.publish.validate_release", lambda *_: release)
    destination = stage_release(
        collection(tmp_path), output, tmp_path / "stage", config(tmp_path)
    )
    files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert files == {
        "README.md",
        "release-manifest.json",
        "data/puzzles/base_game_2026_06_16-00000-of-00001.parquet",
        "data/solutions/base_game_2026_06_16-00000-of-00001.parquet",
        "data/observations/base_game_2026_06_16-00000-of-00001.parquet",
        "data/normalized/base_game_2026_06_16-00000-of-00001.parquet",
    }


@pytest.mark.parametrize("relation", ["equal", "destination_ancestor", "destination_descendant"])
def test_stage_rejects_overlapping_paths_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relation: str
):
    release = manifest("subset")
    root = tmp_path / "root"
    output = root / "out"
    output.mkdir(parents=True)
    (output / "release-manifest.json").write_text("{}", encoding="utf-8")
    for entry in release.configs.values():
        path = output / entry.parquet_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"parquet")
    sentinel = output / "source-sentinel.txt"
    sentinel.write_text("source intact", encoding="utf-8")

    if relation == "equal":
        destination = output
    elif relation == "destination_ancestor":
        destination = root
    else:
        destination = output / "stage"

    monkeypatch.setattr("opus_corpus.publish.validate_release", lambda *_: release)
    with pytest.raises(PublicationError, match="overlap"):
        stage_release(collection(tmp_path), output, destination, config(tmp_path))

    assert sentinel.read_text(encoding="utf-8") == "source intact"
    if relation == "destination_descendant":
        assert not destination.exists()


def test_publish_rejects_subset_before_staging_or_hub_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = manifest("subset")
    monkeypatch.setattr("opus_corpus.publish.validate_release", lambda *_: release)

    def fail_stage(*_args, **_kwargs):
        raise AssertionError("subset release reached staging")

    monkeypatch.setattr("opus_corpus.publish.stage_release", fail_stage)
    with pytest.raises(PublicationError, match="complete"):
        publish_release(
            collection(tmp_path),
            tmp_path / "out",
            config(tmp_path, "owner/dataset"),
        )


@pytest.mark.parametrize(
    "repo_id", ["CHANGE_ME", "YOUR_USERNAME/YOUR_DATASET", "missing-slash", "/bad", "bad/"]
)
def test_publish_refuses_placeholder_or_malformed_repo_ids(tmp_path: Path, repo_id: str):
    with pytest.raises(PublicationError):
        publish_release(collection(tmp_path), tmp_path / "out", config(tmp_path, repo_id))
