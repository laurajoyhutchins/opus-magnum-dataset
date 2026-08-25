from __future__ import annotations

import argparse
from pathlib import Path

from opus_corpus.adapters.official_game import prepare_official_source_root
from opus_corpus.collections import validate_collection


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a runtime-exported official puzzle dump for official-game acquisition."
    )
    parser.add_argument(
        "--collection",
        default="collections/base-game-2026-06-16.toml",
        help="frozen collection manifest",
    )
    parser.add_argument("--dump", required=True, help="fresh dump created by the extractor mod")
    parser.add_argument("--output", required=True, help="fresh official-game source-root path")
    parser.add_argument(
        "--snapshot-id",
        required=True,
        help="operator-supplied identifier for the exact local game snapshot",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    collection = validate_collection(Path(args.collection))
    manifest = prepare_official_source_root(
        collection,
        Path(args.dump),
        Path(args.output),
        snapshot_id=args.snapshot_id,
    )
    print(
        f"prepared {len(manifest.mappings)} official puzzle artifacts at {Path(args.output)} "
        f"for snapshot {manifest.snapshot_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
