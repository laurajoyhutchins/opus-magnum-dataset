from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from .card import render_dataset_card
from .collections import CollectionDefinition
from .config import CorpusConfig
from .errors import PublicationError
from .release import validate_release

_PLACEHOLDERS = {"CHANGE_ME", "YOUR_USERNAME/YOUR_DATASET"}
_REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")


def validate_repo_id(repo_id: str) -> None:
    if repo_id in _PLACEHOLDERS or not _REPO_ID.fullmatch(repo_id):
        raise PublicationError(
            "huggingface.repo_id must be a non-placeholder owner/dataset repository identifier"
        )


def stage_release(
    collection: CollectionDefinition,
    output_dir: Path,
    destination: Path,
    config: CorpusConfig,
) -> Path:
    manifest = validate_release(collection, output_dir, config)
    output_dir = Path(output_dir)
    destination = Path(destination).resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    (destination / "README.md").write_text(
        render_dataset_card(manifest, config.card), encoding="utf-8"
    )
    shutil.copy2(output_dir / "release-manifest.json", destination / "release-manifest.json")
    for entry in manifest.configs.values():
        source = output_dir / entry.parquet_path
        target = destination / entry.parquet_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def publish_release(
    collection: CollectionDefinition,
    output_dir: Path,
    config: CorpusConfig,
    token: str | None = None,
) -> str:
    validate_repo_id(config.huggingface_repo_id)
    manifest = validate_release(collection, output_dir, config)
    if manifest.coverage_policy != "complete":
        raise PublicationError("only complete coverage releases may be published")

    from huggingface_hub import HfApi

    with tempfile.TemporaryDirectory(prefix="opus-corpus-hub-") as temporary_directory:
        staged = stage_release(collection, output_dir, Path(temporary_directory), config)
        api = HfApi(token=token)
        api.create_repo(
            repo_id=config.huggingface_repo_id,
            repo_type="dataset",
            private=config.huggingface_private,
            exist_ok=True,
        )
        result = api.upload_folder(
            repo_id=config.huggingface_repo_id,
            repo_type="dataset",
            folder_path=staged,
            delete_patterns="**",
            commit_message=f"Publish {collection.collection_id}",
        )
    return str(result)
