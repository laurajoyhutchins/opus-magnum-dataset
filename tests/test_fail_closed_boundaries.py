from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from opus_corpus.cli import main
from opus_corpus.collections import validate_collection
from opus_corpus.config import load_config
from opus_corpus.errors import CollectionValidationError, ConfigurationError, ReleaseValidationError
from opus_corpus.release import ConfigRelease, ReleaseManifest, validate_release
from opus_corpus.release_configs import CONFIG_NAMES
from opus_corpus.release_inputs import load_release_inputs


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _config_with_replacement(tmp_path: Path, old: str, new: str) -> Path:
    source = (_repo_root() / "corpus.toml").read_text(encoding="utf-8")
    assert old in source
    path = tmp_path / "corpus.toml"
    path.write_text(source.replace(old, new), encoding="utf-8")
    return path


def _release_validation_fixture(
    tmp_path: Path,
) -> tuple[ReleaseManifest, SimpleNamespace, SimpleNamespace]:
    configs: dict[str, ConfigRelease] = {}
    for config_name in CONFIG_NAMES:
        parquet_path = tmp_path / "data" / config_name / f"{config_name}.parquet"
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_path.write_bytes(b"fixture")
        configs[config_name] = ConfigRelease(
            schema_path=f"schemas/{config_name}.json",
            schema_sha256="schema",
            records_sha256="r" * 64,
            row_count=0,
            parquet_path=parquet_path.relative_to(tmp_path).as_posix(),
            parquet_sha256="p" * 64,
            source_path=f"{config_name}.jsonl",
            source_sha256="s" * 64,
        )
    manifest = ReleaseManifest(
        format_version=2,
        corpus_schema_version="0.1",
        collection_id="fixture",
        collection_inventory_sha256="a" * 64,
        split="fixture",
        build_software_revision=None,
        build_config_sha256="b" * 64,
        payload_policy="metadata-only",
        coverage_policy="subset",
        release_metadata={"coverage": {}},
        release_metadata_sha256="c" * 64,
        configs=configs,
        logical_release_sha256="d" * 64,
    )
    config_path = tmp_path / "corpus.toml"
    config_path.write_text("placeholder", encoding="utf-8")
    config = SimpleNamespace(path=config_path)
    collection = SimpleNamespace(collection_id="fixture", inventory_sha256="a" * 64)
    return manifest, config, collection


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("schema_version = 1", "schema_version = true", "corpus.schema_version"),
        ('output_root = ".release"', "output_root = false", "corpus.output_root"),
        ('compression = "zstd"', "compression = false", "parquet.compression"),
        ("use_dictionary = true", 'use_dictionary = "false"', "parquet.use_dictionary"),
        ("write_statistics = true", "write_statistics = 1", "parquet.write_statistics"),
        (
            'config_names = ["puzzles", "solutions", "observations", "normalized"]',
            'config_names = "puzzles"',
            "release.config_names",
        ),
        (
            'payload_policy_default = "metadata-only"',
            "payload_policy_default = false",
            "release.payload_policy_default",
        ),
        (
            'repo_id = "laurajoyhutchins/opus-magnum"',
            "repo_id = false",
            "huggingface.repo_id",
        ),
        ("private = false", 'private = "false"', "huggingface.private"),
        ('title = "Opus Magnum Dataset"', "title = false", "card.title"),
    ],
)
def test_load_config_rejects_wrong_toml_scalar_types(
    tmp_path: Path, old: str, new: str, field: str
):
    path = _config_with_replacement(tmp_path, old, new)
    with pytest.raises(ConfigurationError, match=field):
        load_config(path)


def test_load_config_preserves_defaults_for_omitted_optional_fields(tmp_path: Path):
    text = (_repo_root() / "corpus.toml").read_text(encoding="utf-8")
    for line in (
        'output_root = ".release"\n',
        'compression = "zstd"\n',
        "use_dictionary = true\n",
        "write_statistics = true\n",
        "private = false\n",
    ):
        text = text.replace(line, "")
    path = tmp_path / "corpus.toml"
    path.write_text(text, encoding="utf-8")

    config = load_config(path)

    assert config.output_root == tmp_path / ".release"
    assert config.compression == "zstd"
    assert config.use_dictionary is True
    assert config.write_statistics is True
    assert config.huggingface_private is False


def test_collection_hash_oserror_becomes_validation_error(monkeypatch: pytest.MonkeyPatch):
    manifest = _repo_root() / "collections/base-game-2026-06-16.toml"

    def fail_hash(path: Path) -> str:
        raise OSError("inventory hash read failed")

    monkeypatch.setattr("opus_corpus.collections.sha256_file", fail_hash)

    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)

    assert "inventory_read_error" in {error.code for error in exc.value.errors}
    assert "inventory hash read failed" in str(exc.value)


def test_collection_read_oserror_becomes_validation_error(monkeypatch: pytest.MonkeyPatch):
    manifest = _repo_root() / "collections/base-game-2026-06-16.toml"
    original = Path.read_text

    def fail_inventory_read(self: Path, *args, **kwargs) -> str:
        if self.suffix == ".csv":
            raise OSError("inventory disappeared during read")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_inventory_read)

    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(manifest)

    assert "inventory_read_error" in {error.code for error in exc.value.errors}
    assert "inventory disappeared during read" in str(exc.value)


def test_release_input_read_oserror_becomes_validation_error(monkeypatch: pytest.MonkeyPatch):
    input_dir = _repo_root() / "fixtures/tiny-corpus"
    original = Path.read_text

    def fail_input_read(self: Path, *args, **kwargs) -> str:
        if self.name == "puzzles.jsonl":
            raise OSError("input disappeared during read")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_input_read)

    with pytest.raises(ReleaseValidationError) as exc:
        load_release_inputs(input_dir)

    assert "input_read_error" in {error.code for error in exc.value.errors}
    assert "input disappeared during read" in str(exc.value)


def test_release_input_hash_oserror_becomes_validation_error(monkeypatch: pytest.MonkeyPatch):
    input_dir = _repo_root() / "fixtures/tiny-corpus"

    def fail_hash(path: Path) -> str:
        raise OSError(f"cannot hash {path.name}")

    monkeypatch.setattr("opus_corpus.release_inputs.sha256_file", fail_hash)

    with pytest.raises(ReleaseValidationError) as exc:
        load_release_inputs(input_dir)

    assert "input_hash_error" in {error.code for error in exc.value.errors}
    assert "cannot hash" in str(exc.value)


def test_release_config_hash_oserror_becomes_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manifest = ReleaseManifest(
        format_version=2,
        corpus_schema_version="0.1",
        collection_id="fixture",
        collection_inventory_sha256="a" * 64,
        split="fixture",
        build_software_revision=None,
        build_config_sha256="b" * 64,
        payload_policy="metadata-only",
        coverage_policy="subset",
        release_metadata={"coverage": {}},
        release_metadata_sha256="c" * 64,
        configs={},
        logical_release_sha256="d" * 64,
    )
    config_path = tmp_path / "corpus.toml"
    config_path.write_text("placeholder", encoding="utf-8")
    config = SimpleNamespace(path=config_path)
    collection = SimpleNamespace(collection_id="fixture", inventory_sha256="a" * 64)

    monkeypatch.setattr("opus_corpus.release._read_manifest", lambda *_: manifest)

    def fail_hash(path: Path) -> str:
        raise OSError("config hash read failed")

    monkeypatch.setattr("opus_corpus.release.sha256_file", fail_hash)

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(collection, tmp_path, config)

    assert "build_config_read_error" in {error.code for error in exc.value.errors}
    assert "config hash read failed" in str(exc.value)


def test_release_parquet_hash_oserror_becomes_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manifest, config, collection = _release_validation_fixture(tmp_path)
    monkeypatch.setattr("opus_corpus.release._read_manifest", lambda *_: manifest)
    monkeypatch.setattr(
        "opus_corpus.release.load_schema_resource",
        lambda *_: SimpleNamespace(sha256="schema", logical_path="schema"),
    )

    def fail_parquet_hash(path: Path) -> str:
        if path == config.path:
            return manifest.build_config_sha256
        raise OSError("parquet hash read failed")

    monkeypatch.setattr("opus_corpus.release.sha256_file", fail_parquet_hash)

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(collection, tmp_path, config)

    assert "parquet_read_error" in {error.code for error in exc.value.errors}
    assert "parquet hash read failed" in str(exc.value)


def test_release_parquet_read_oserror_becomes_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manifest, config, collection = _release_validation_fixture(tmp_path)
    monkeypatch.setattr("opus_corpus.release._read_manifest", lambda *_: manifest)
    monkeypatch.setattr(
        "opus_corpus.release.load_schema_resource",
        lambda *_: SimpleNamespace(sha256="schema", logical_path="schema"),
    )
    monkeypatch.setattr(
        "opus_corpus.release.sha256_file",
        lambda path: manifest.build_config_sha256 if path == config.path else "p" * 64,
    )

    def fail_parquet_read(*_args, **_kwargs):
        raise OSError("parquet read failed")

    monkeypatch.setattr("opus_corpus.release.read_parquet", fail_parquet_read)

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(collection, tmp_path, config)

    assert "parquet_read_error" in {error.code for error in exc.value.errors}
    assert "parquet read failed" in str(exc.value)


def test_cli_malformed_config_uses_stable_error_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    path = _config_with_replacement(
        tmp_path,
        "use_dictionary = true",
        'use_dictionary = "false"',
    )

    assert main(["--config", str(path), "collections", "validate"]) == 2
    assert "parquet.use_dictionary" in capsys.readouterr().err
