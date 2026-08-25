from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition, validate_collection
from opus_corpus.config import CorpusConfig, load_config
from opus_corpus.publish import stage_release
from opus_corpus.release import ConfigRelease, ReleaseManifest, build_release


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sibling_names(destination: Path) -> tuple[str, ...]:
    return tuple(sorted(path.name for path in destination.parent.iterdir()))


def _real_release_inputs() -> tuple[Path, CorpusConfig, CollectionDefinition]:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "corpus.toml")
    collection = validate_collection(root / "collections/base-game-2026-06-16.toml")
    return root, config, collection


def _build_tiny_release(output: Path) -> None:
    root, config, collection = _real_release_inputs()
    build_release(
        collection,
        root / "fixtures/tiny-corpus",
        output,
        config,
        "metadata-only",
        coverage_policy="subset",
    )


def test_failed_release_build_preserves_prior_release_byte_for_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("pyarrow")
    output = tmp_path / "release"
    _build_tiny_release(output)
    before = _snapshot_tree(output)
    siblings_before = _sibling_names(output)
    root, config, collection = _real_release_inputs()
    writes = 0

    def fail_after_partial_write(
        _config_name: str,
        _rows: list[dict],
        path: Path,
        _config: CorpusConfig,
    ) -> None:
        nonlocal writes
        writes += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"partial-{writes}".encode())
        if writes == 2:
            raise RuntimeError("injected parquet failure")

    monkeypatch.setattr("opus_corpus.release.write_parquet", fail_after_partial_write)

    with pytest.raises(RuntimeError, match="injected parquet failure"):
        build_release(
            collection,
            root / "fixtures/tiny-corpus",
            output,
            config,
            "metadata-only",
            coverage_policy="subset",
        )

    assert writes == 2
    assert _snapshot_tree(output) == before
    assert _sibling_names(output) == siblings_before


def test_release_build_validates_candidate_before_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("pyarrow")
    output = tmp_path / "release"
    _build_tiny_release(output)
    before = _snapshot_tree(output)
    siblings_before = _sibling_names(output)
    root, config, collection = _real_release_inputs()
    validated: list[Path] = []

    def reject_candidate(
        _collection: CollectionDefinition,
        candidate: Path,
        _config: CorpusConfig,
    ) -> ReleaseManifest:
        validated.append(Path(candidate))
        raise RuntimeError("candidate validation failed")

    monkeypatch.setattr("opus_corpus.release.validate_release", reject_candidate)

    with pytest.raises(RuntimeError, match="candidate validation failed"):
        build_release(
            collection,
            root / "fixtures/tiny-corpus",
            output,
            config,
            "metadata-only",
            coverage_policy="subset",
        )

    assert len(validated) == 1
    assert validated[0] != output
    assert validated[0].parent == output.parent
    assert _snapshot_tree(output) == before
    assert _sibling_names(output) == siblings_before


def test_release_build_rolls_back_if_candidate_promotion_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("pyarrow")
    output = tmp_path / "release"
    _build_tiny_release(output)
    before = _snapshot_tree(output)
    siblings_before = _sibling_names(output)
    root, config, collection = _real_release_inputs()
    real_replace = Path.replace
    failed = False

    def fail_candidate_promotion(self: Path, target: str | Path) -> Path:
        nonlocal failed
        if Path(target) == output and not failed:
            failed = True
            raise OSError("injected promotion failure")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_candidate_promotion)

    with pytest.raises(OSError, match="injected promotion failure"):
        build_release(
            collection,
            root / "fixtures/tiny-corpus",
            output,
            config,
            "metadata-only",
            coverage_policy="subset",
        )

    assert failed
    assert _snapshot_tree(output) == before
    assert _sibling_names(output) == siblings_before


def test_successful_release_build_replaces_tree_exactly(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    output = tmp_path / "release"
    _build_tiny_release(output)
    expected = _snapshot_tree(output)
    (output / "stale.txt").write_bytes(b"must disappear")
    stale_nested = output / "data" / "stale" / "old.parquet"
    stale_nested.parent.mkdir(parents=True)
    stale_nested.write_bytes(b"old")
    siblings_before = _sibling_names(output)

    _build_tiny_release(output)

    assert _snapshot_tree(output) == expected
    assert _sibling_names(output) == siblings_before


def _stage_manifest() -> ReleaseManifest:
    configs = {
        name: ConfigRelease(
            schema_path=f"schemas/{name}.schema.json",
            schema_sha256="a" * 64,
            records_sha256="b" * 64,
            row_count=1,
            parquet_path=f"data/{name}/fixture-00000-of-00001.parquet",
            parquet_sha256="c" * 64,
            source_path=f"fixtures/{name}.jsonl",
            source_sha256="d" * 64,
        )
        for name in ("puzzles", "solutions", "observations", "normalized")
    }
    return ReleaseManifest(
        format_version=2,
        corpus_schema_version="0.1",
        collection_id="fixture-collection",
        collection_inventory_sha256="e" * 64,
        split="fixture_collection",
        build_software_revision=None,
        build_config_sha256="f" * 64,
        payload_policy="metadata-only",
        coverage_policy="subset",
        release_metadata={"coverage": {}},
        release_metadata_sha256="0" * 64,
        configs=configs,
        logical_release_sha256="1" * 64,
    )


def _stage_collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture-collection",
        inventory_sha256="e" * 64,
        puzzle_count=0,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=(),
        manifest={},
    )


def _stage_config(tmp_path: Path) -> CorpusConfig:
    path = tmp_path / "corpus.toml"
    path.write_text("fixture", encoding="utf-8")
    return CorpusConfig(
        root=tmp_path,
        path=path,
        schema_version=1,
        output_root=tmp_path / ".release",
        config_names=("puzzles", "solutions", "observations", "normalized"),
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
        payload_policy_default="metadata-only",
        huggingface_repo_id="CHANGE_ME",
        huggingface_private=False,
        card={"title": "Fixture", "purpose": "Transactional staging regression."},
    )


def _write_stage_source(output: Path, manifest: ReleaseManifest) -> None:
    output.mkdir()
    (output / "release-manifest.json").write_text("{}\n", encoding="utf-8")
    for index, entry in enumerate(manifest.configs.values(), start=1):
        path = output / entry.parquet_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"parquet-{index}".encode())


def test_failed_staging_preserves_prior_destination_byte_for_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _stage_manifest()
    collection = _stage_collection(tmp_path)
    config = _stage_config(tmp_path)
    output = tmp_path / "release"
    destination = tmp_path / "stage"
    _write_stage_source(output, manifest)
    monkeypatch.setattr("opus_corpus.publish.validate_release", lambda *_: manifest)
    stage_release(collection, output, destination, config)
    before = _snapshot_tree(destination)
    siblings_before = _sibling_names(destination)
    real_copy2 = shutil.copy2
    copies = 0

    def fail_after_partial_copy(source: Path, target: Path, *args, **kwargs):
        nonlocal copies
        copies += 1
        result = real_copy2(source, target, *args, **kwargs)
        if copies == 2:
            raise OSError("injected staging failure")
        return result

    monkeypatch.setattr("opus_corpus.publish.shutil.copy2", fail_after_partial_copy)

    with pytest.raises(OSError, match="injected staging failure"):
        stage_release(collection, output, destination, config)

    assert copies == 2
    assert _snapshot_tree(destination) == before
    assert _sibling_names(destination) == siblings_before


def test_successful_staging_replaces_tree_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _stage_manifest()
    collection = _stage_collection(tmp_path)
    config = _stage_config(tmp_path)
    output = tmp_path / "release"
    destination = tmp_path / "stage"
    _write_stage_source(output, manifest)
    monkeypatch.setattr("opus_corpus.publish.validate_release", lambda *_: manifest)
    stage_release(collection, output, destination, config)
    expected = _snapshot_tree(destination)
    (destination / "stale.txt").write_bytes(b"must disappear")
    siblings_before = _sibling_names(destination)

    stage_release(collection, output, destination, config)

    assert _snapshot_tree(destination) == expected
    assert _sibling_names(destination) == siblings_before
