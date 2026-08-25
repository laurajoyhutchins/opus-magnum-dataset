from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from opus_corpus.cli import main
from opus_corpus.collections import validate_collection
from opus_corpus.config import load_config
from opus_corpus.errors import CollectionValidationError, ConfigurationError, ReleaseValidationError
from opus_corpus.release import build_release, validate_release
from opus_corpus.release_inputs import load_release_inputs


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _copy_tiny_inputs(tmp_path: Path) -> Path:
    input_dir = tmp_path / "tiny-corpus"
    shutil.copytree(_repo_root() / "fixtures/tiny-corpus", input_dir)
    return input_dir


def test_invalid_utf8_config_is_a_configuration_error(tmp_path: Path):
    path = tmp_path / "corpus.toml"
    path.write_bytes(b"\xff")

    with pytest.raises(ConfigurationError, match="invalid configuration"):
        load_config(path)


def test_invalid_utf8_config_uses_stable_cli_error_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "corpus.toml"
    path.write_bytes(b"\xff")

    assert main(["--config", str(path), "collections", "validate"]) == 2
    assert "invalid configuration" in capsys.readouterr().err


def test_invalid_utf8_collection_manifest_is_a_validation_error(tmp_path: Path):
    path = tmp_path / "collection.toml"
    path.write_bytes(b"\xff")

    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(path)

    assert {error.code for error in exc.value.errors} == {"manifest_parse_error"}


def test_invalid_utf8_release_input_is_a_validation_error(tmp_path: Path):
    input_dir = _copy_tiny_inputs(tmp_path)
    (input_dir / "puzzles.jsonl").write_bytes(b"\xff")

    with pytest.raises(ReleaseValidationError) as exc:
        load_release_inputs(input_dir)

    assert "input_decode_error" in {error.code for error in exc.value.errors}


def test_invalid_utf8_release_metadata_is_a_validation_error(tmp_path: Path):
    input_dir = _copy_tiny_inputs(tmp_path)
    (input_dir / "release-metadata.json").write_bytes(b"\xff")
    root = _repo_root()
    collection = validate_collection(root / "collections/base-game-2026-06-16.toml")
    config = load_config(root / "corpus.toml")

    with pytest.raises(ReleaseValidationError) as exc:
        build_release(
            collection,
            input_dir,
            tmp_path / "release",
            config,
            "metadata-only",
            coverage_policy="subset",
        )

    assert "release_metadata_invalid" in {error.code for error in exc.value.errors}


def test_invalid_utf8_release_manifest_is_a_validation_error(tmp_path: Path):
    output_dir = tmp_path / "release"
    output_dir.mkdir()
    (output_dir / "release-manifest.json").write_bytes(b"\xff")

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(object(), output_dir, object())

    assert {error.code for error in exc.value.errors} == {"release_manifest_invalid"}


@pytest.mark.parametrize(
    "replacement",
    [
        {"configs": []},
        {"release_metadata": ["invalid"]},
    ],
)
def test_malformed_release_manifest_containers_are_validation_errors(
    tmp_path: Path, replacement: dict[str, object]
):
    output_dir = tmp_path / "release"
    output_dir.mkdir()
    manifest: dict[str, object] = {
        "format_version": 2,
        "corpus_schema_version": "0.1",
        "collection_id": "fixture",
        "collection_inventory_sha256": "a" * 64,
        "split": "fixture",
        "build_software_revision": None,
        "build_config_sha256": "b" * 64,
        "payload_policy": "metadata-only",
        "coverage_policy": "subset",
        "release_metadata": {},
        "release_metadata_sha256": "c" * 64,
        "configs": {},
        "logical_release_sha256": "d" * 64,
    }
    manifest.update(replacement)
    (output_dir / "release-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(object(), output_dir, object())

    assert {error.code for error in exc.value.errors} == {"release_manifest_invalid"}
