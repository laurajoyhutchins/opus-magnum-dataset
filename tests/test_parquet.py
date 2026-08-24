from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.collections import CollectionDefinition
from opus_corpus.config import CorpusConfig
from opus_corpus.release import build_release, validate_release

pytest.importorskip("pyarrow")


def config(root: Path) -> CorpusConfig:
    path = root / "corpus.toml"
    path.write_text("fixture-config\n", encoding="utf-8")
    return CorpusConfig(
        root=root,
        path=path,
        schema_version=1,
        schemas_dir=Path(__file__).resolve().parents[1] / "schemas",
        output_root=root / ".release",
        config_names=("puzzles", "solutions", "observations", "normalized"),
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
        payload_policy_default="metadata-only",
        huggingface_repo_id="CHANGE_ME",
        huggingface_private=False,
        card={},
    )


def collection(tmp_path: Path) -> CollectionDefinition:
    manifest = tmp_path / "base-game-2026-06-16.toml"
    inventory = tmp_path / "base-game-2026-06-16.csv"
    return CollectionDefinition(
        collection_id="base-game-2026-06-16",
        inventory_sha256="a" * 64,
        puzzle_count=166,
        manifest_path=manifest,
        inventory_path=inventory,
        inventory_rows=(),
        manifest={},
    )


def test_tiny_release_builds_and_validates(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "release"
    cfg = config(tmp_path)
    built = build_release(
        collection(tmp_path), root / "fixtures/tiny-corpus", output, cfg, "metadata-only"
    )
    assert set(built.configs) == {"puzzles", "solutions", "observations", "normalized"}
    assert built.split == "base_game_2026_06_16"
    for name in built.configs:
        assert (output / built.configs[name].parquet_path).is_file()
    validated = validate_release(collection(tmp_path), output, cfg)
    assert validated.logical_release_sha256 == built.logical_release_sha256


def test_repeated_builds_have_identical_logical_hashes(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    cfg = config(tmp_path)
    first = build_release(
        collection(tmp_path),
        root / "fixtures/tiny-corpus",
        tmp_path / "one",
        cfg,
        "metadata-only",
    )
    second = build_release(
        collection(tmp_path),
        root / "fixtures/tiny-corpus",
        tmp_path / "two",
        cfg,
        "metadata-only",
    )
    assert first.logical_release_sha256 == second.logical_release_sha256
    assert {name: value.records_sha256 for name, value in first.configs.items()} == {
        name: value.records_sha256 for name, value in second.configs.items()
    }
