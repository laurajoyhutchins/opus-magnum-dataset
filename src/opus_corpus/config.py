from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import ConfigurationError
from .release_configs import CONFIG_NAMES
from .schema_resources import collect_schema_errors, load_schema_resource

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
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"invalid configuration: {exc}") from exc

    validator = Draft202012Validator(
        load_schema_resource("corpus-config.schema.json").schema
    )
    errors = collect_schema_errors(
        validator,
        raw,
        code="configuration_schema_error",
        path=config_path.as_posix(),
    )
    if errors:
        detail = "; ".join(error.detail for error in errors)
        raise ConfigurationError(f"invalid configuration: {detail}")

    corpus = raw["corpus"]
    parquet = raw["parquet"]
    release = raw["release"]
    huggingface = raw["huggingface"]
    card = raw.get("card", {})

    schema_version = corpus["schema_version"]
    output_root = corpus.get("output_root", ".release")
    compression = parquet.get("compression", "zstd")
    use_dictionary = parquet.get("use_dictionary", True)
    write_statistics = parquet.get("write_statistics", True)

    config_names = tuple(release["config_names"])
    if config_names != REQUIRED_CONFIGS:
        raise ConfigurationError(f"release.config_names must be {list(REQUIRED_CONFIGS)!r}")

    payload_policy_default = release["payload_policy_default"]
    repo_id = huggingface["repo_id"]
    private = huggingface.get("private", False)
    card_settings = dict(card)

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
