from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError
from .release_configs import CONFIG_NAMES

REQUIRED_CONFIGS = CONFIG_NAMES


@dataclass(frozen=True)
class CorpusConfig:
    root: Path
    path: Path
    schema_version: int
    output_root: Path
    config_names: tuple[str, ...]
    compression: str
    use_dictionary: bool
    write_statistics: bool
    payload_policy_default: str
    huggingface_repo_id: str
    huggingface_private: bool
    card: dict[str, str]


def load_config(path: Path | str = "corpus.toml") -> CorpusConfig:
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"configuration file not found: {config_path}")
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"invalid configuration: {exc}") from exc

    corpus = raw.get("corpus")
    parquet = raw.get("parquet")
    release = raw.get("release")
    huggingface = raw.get("huggingface")
    card = raw.get("card", {})
    for field, value in (
        ("corpus", corpus),
        ("parquet", parquet),
        ("release", release),
        ("huggingface", huggingface),
        ("card", card),
    ):
        if not isinstance(value, dict):
            raise ConfigurationError(f"{field} must be a TOML table")

    schema_version = corpus.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        raise ConfigurationError("corpus.schema_version must be the integer 1")

    output_root = corpus.get("output_root", ".release")
    if not isinstance(output_root, str):
        raise ConfigurationError("corpus.output_root must be a string")

    compression = parquet.get("compression", "zstd")
    if not isinstance(compression, str):
        raise ConfigurationError("parquet.compression must be a string")
    use_dictionary = parquet.get("use_dictionary", True)
    if not isinstance(use_dictionary, bool):
        raise ConfigurationError("parquet.use_dictionary must be true or false")
    write_statistics = parquet.get("write_statistics", True)
    if not isinstance(write_statistics, bool):
        raise ConfigurationError("parquet.write_statistics must be true or false")

    config_names_value = release.get("config_names")
    if not isinstance(config_names_value, list) or not all(
        isinstance(value, str) for value in config_names_value
    ):
        raise ConfigurationError("release.config_names must be an array of strings")
    config_names = tuple(config_names_value)
    if config_names != REQUIRED_CONFIGS:
        raise ConfigurationError(f"release.config_names must be {list(REQUIRED_CONFIGS)!r}")

    payload_policy_default = release.get("payload_policy_default")
    if not isinstance(payload_policy_default, str):
        raise ConfigurationError("release.payload_policy_default must be a string")
    if payload_policy_default not in {"metadata-only", "include-permitted"}:
        raise ConfigurationError(
            "release.payload_policy_default must be metadata-only or include-permitted"
        )

    repo_id = huggingface.get("repo_id")
    private = huggingface.get("private", False)
    if not isinstance(repo_id, str) or not repo_id:
        raise ConfigurationError("huggingface.repo_id must be a non-empty string")
    if not isinstance(private, bool):
        raise ConfigurationError("huggingface.private must be true or false")

    card_settings: dict[str, str] = {}
    for key, value in card.items():
        if not isinstance(value, str):
            raise ConfigurationError(f"card.{key} must be a string")
        card_settings[key] = value

    return CorpusConfig(
        root=config_path.parent,
        path=config_path,
        schema_version=schema_version,
        output_root=config_path.parent / output_root,
        config_names=config_names,
        compression=compression,
        use_dictionary=use_dictionary,
        write_statistics=write_statistics,
        payload_policy_default=payload_policy_default,
        huggingface_repo_id=repo_id,
        huggingface_private=private,
        card=card_settings,
    )
