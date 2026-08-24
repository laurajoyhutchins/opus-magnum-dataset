# Official local puzzle-byte acquisition

The `official-game` adapter is the explicit local path for exact official Opus Magnum `.puzzle` bytes. It does not auto-discover game installations, infer puzzle identities from filenames, parse game fields, or create a second object store.

## Source-root contract

Pass a local directory containing `official-puzzles.toml` plus the referenced `.puzzle` files:

```toml
schema_version = 1
snapshot_id = "my-local-snapshot"

[[puzzles]]
puzzle_id = "om.puzzle.0001"
path = "campaign/P007.puzzle"

[[puzzles]]
puzzle_id = "om.puzzle.0002"
path = "campaign/P008.puzzle"
```

`puzzle_id` must be a canonical ID in the selected collection. `path` is a POSIX-style relative path below the source root and must end in `.puzzle`. The same puzzle ID or path may appear only once. `snapshot_id` is a stable local provenance label and may contain only letters, digits, `.`, `_`, and `-`, beginning with a letter or digit.

The manifest may name only the locally available official bytes being acquired. The adapter does not substitute molecule-database semantics or synthesize missing official puzzle payloads.

## Fetch

```sh
opus-corpus fetch base-game-2026-06-16 \
  --source official-game \
  --source-root /path/to/local/official-puzzles \
  --cache .cache
```

`--source-root` is required for `official-game`; there is intentionally no guessed fallback path.

Before mutating the cache, the adapter validates the complete manifest, checks each resolved path remains within the source root, requires every referenced file to exist, and reads the exact file bytes. Ambiguous or unsafe manifests fail closed.

## Cache facts and rights

Successful acquisition writes through the existing `ContentAddressedCache` only:

- object identity is the SHA-256 of the exact `.puzzle` bytes;
- provenance uses source `official-game`, revision `local:<snapshot_id>`, and the manifest-relative upstream path;
- rights status is always `local_fetch_only`;
- local absolute paths are not recorded in provenance;
- reusing the same snapshot ID and upstream path with different bytes is rejected by the cache's pinned-source integrity check.

This path acquires source facts only. Canonical `PuzzleArtifact` materialization, simulation/verification, normalized puzzle generation, and release inclusion remain separate downstream responsibilities.
