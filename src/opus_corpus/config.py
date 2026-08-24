from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

REQUIRED_CONFIGS = ("puzzles", "solutions", "observations", "normalized")


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
    card: dict[str, Any]


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
    if not all(isinstance(value, dict) for value in (corpus, parquet, release, huggingface, card)):
        raise ConfigurationError(
            "corpus.toml requires [corpus], [parquet], [release], [huggingface], and [card] tables"
        )

    schema_version = corpus.get("schema_version")
    if schema_version != 1:
        raise ConfigurationError("corpus.schema_version must be 1")
    output_root = corpus.get("output_root", ".release")
    config_names = tuple(release.get("config_names", ()))
    if config_names != REQUIRED_CONFIGS:
        raise ConfigurationError(f"release.config_names must be {list(REQUIRED_CONFIGS)!r}")
    payload_policy_default = release.get("payload_policy_default")
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

    return CorpusConfig(
        root=config_path.parent,
        path=config_path,
        schema_version=1,
        output_root=config_path.parent / str(output_root),
        config_names=config_names,
        compression=str(parquet.get("compression", "zstd")),
        use_dictionary=bool(parquet.get("use_dictionary", True)),
        write_statistics=bool(parquet.get("write_statistics", True)),
        payload_policy_default=payload_policy_default,
        huggingface_repo_id=repo_id,
        huggingface_private=private,
        card=dict(card),
    )
