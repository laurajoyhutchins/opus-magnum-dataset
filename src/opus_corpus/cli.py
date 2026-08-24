from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .adapters import ADAPTERS, OfficialGameAdapter
from .collections import validate_all_collections, validate_collection
from .config import load_config
from .errors import ConfigurationError, CorpusError, PublicationError, ValidationFailure
from .publish import publish_release, stage_release
from .release import build_release, validate_release


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opus-corpus")
    parser.add_argument("--config", default="corpus.toml", help="repository corpus configuration")
    commands = parser.add_subparsers(dest="command", required=True)

    collections = commands.add_parser("collections")
    collection_commands = collections.add_subparsers(dest="collection_command", required=True)
    collection_validate = collection_commands.add_parser("validate")
    collection_validate.add_argument("manifest", nargs="?")

    fetch = commands.add_parser("fetch")
    fetch.add_argument("collection")
    fetch.add_argument("--source", required=True, choices=tuple(sorted(ADAPTERS)))
    fetch.add_argument("--cache", default=".cache")
    fetch.add_argument(
        "--source-root",
        help="explicit local source root used by the official-game adapter",
    )

    release = commands.add_parser("release")
    release_commands = release.add_subparsers(dest="release_command", required=True)

    build = release_commands.add_parser("build")
    build.add_argument("collection")
    build.add_argument("--input", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--payload-policy", choices=("metadata-only", "include-permitted"))
    build.add_argument(
        "--coverage-policy",
        choices=("complete", "subset"),
        default="complete",
        help="require verified coverage for the full collection or allow an explicit subset",
    )

    validate = release_commands.add_parser("validate")
    validate.add_argument("collection")
    validate.add_argument("--output", required=True)

    stage = release_commands.add_parser("stage")
    stage.add_argument("collection")
    stage.add_argument("--output", required=True)
    stage.add_argument("--destination", required=True)

    publish = release_commands.add_parser("publish")
    publish.add_argument("collection")
    publish.add_argument("--output", required=True)
    return parser


def _collection_from_id(config_path: str, collection_id: str):
    config = load_config(config_path)
    manifest = config.root / "collections" / f"{collection_id}.toml"
    return config, validate_collection(manifest)


def _run(args: argparse.Namespace) -> int:
    if args.command == "collections" and args.collection_command == "validate":
        if args.manifest:
            definitions = [validate_collection(Path(args.manifest))]
        else:
            config = load_config(args.config)
            definitions = validate_all_collections(config.root)
        for definition in definitions:
            print(
                f"valid collection {definition.collection_id}: "
                f"{definition.puzzle_count} puzzles, inventory {definition.inventory_sha256}"
            )
        return 0

    config, collection = _collection_from_id(args.config, args.collection)
    if args.command == "fetch":
        if args.source == "official-game":
            if not args.source_root:
                raise ConfigurationError(
                    "official-game acquisition requires --source-root "
                    "pointing to local puzzle bytes"
                )
            adapter = OfficialGameAdapter(Path(args.source_root))
        else:
            adapter = ADAPTERS[args.source]()
        result = adapter.fetch(collection, Path(args.cache))
        print(
            f"fetched {result.source_id}: {result.candidate_count} candidates across "
            f"{result.puzzles_covered} puzzles"
        )
        return 0

    if args.release_command == "build":
        policy = args.payload_policy or config.payload_policy_default
        manifest = build_release(
            collection,
            Path(args.input),
            Path(args.output),
            config,
            policy,
            coverage_policy=args.coverage_policy,
        )
        print(
            f"built {manifest.collection_id} ({manifest.split}) "
            f"logical_release_sha256={manifest.logical_release_sha256}"
        )
        return 0
    if args.release_command == "validate":
        manifest = validate_release(collection, Path(args.output), config)
        print(
            f"valid release {manifest.collection_id}: "
            f"logical_release_sha256={manifest.logical_release_sha256}"
        )
        return 0
    if args.release_command == "stage":
        destination = stage_release(
            collection, Path(args.output), Path(args.destination), config
        )
        print(f"staged {collection.collection_id} at {destination}")
        return 0
    if args.release_command == "publish":
        result = publish_release(
            collection,
            Path(args.output),
            config,
            token=os.environ.get("HF_TOKEN"),
        )
        print(result)
        return 0
    raise ConfigurationError("unsupported command")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except ValidationFailure as exc:
        for error in exc.errors:
            print(error.render(), file=sys.stderr)
        return 1
    except (ConfigurationError, PublicationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CorpusError as exc:
        print(str(exc), file=sys.stderr)
        return 2
