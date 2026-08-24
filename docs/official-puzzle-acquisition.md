# Official local puzzle-byte acquisition

The `official-game` adapter is the explicit local path for exact official Opus Magnum `.puzzle` bytes. It does not auto-discover game installations, infer puzzle identities from filenames, parse game fields, or create a second object store.

This capability is WP-07 in the repository work graph and lands through PR #16. Downstream puzzle-artifact materialization should consume these cached facts rather than re-reading mutable local source roots.

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

`puzzle_id` must be a canonical ID in the selected collection. `path` is a POSIX-style relative path below the source root and must end in `.puzzle`. The same puzzle ID or path may appear only once. `snapshot_id` is a stable local provenance label and may contain only letters, digits, `.`, `_`, and `-`, beginning with a letter or digit. Reusing a snapshot ID means reusing the same immutable local snapshot, including the exact manifest mapping.

The manifest may name only the locally available official bytes being acquired. The adapter does not substitute molecule-database semantics or synthesize missing official puzzle payloads.

## Fetch

```sh
opus-corpus fetch base-game-2026-06-16 \
  --source official-game \
  --source-root /path/to/local/official-puzzles \
  --cache .cache
```

`--source-root` is required for `official-game`; there is intentionally no guessed fallback path.

Before mutating the cache, the adapter validates the complete manifest, checks each resolved path remains within the source root, requires every referenced file to exist, and reads the exact manifest and puzzle-file bytes. Ambiguous or unsafe manifests fail closed.

## Cache facts and rights

Successful acquisition writes through the existing `ContentAddressedCache` only:

- object identity is the SHA-256 of the exact cached source bytes;
- the exact `official-puzzles.toml` bytes are cached as a source fact, preserving the canonical puzzle-ID-to-path mapping needed for offline materialization;
- provenance uses source `official-game`, a filesystem-safe revision `local-<sha256(snapshot_id)>`, and manifest-relative upstream paths;
- the original `snapshot_id` remains present in the cached manifest rather than being embedded verbatim in a filesystem path;
- rights status is always `local_fetch_only` for both the manifest and puzzle bytes;
- local absolute paths are not recorded in provenance;
- reusing the same snapshot ID with different manifest bytes, including a changed puzzle-ID mapping, is rejected by the cache's pinned-source integrity check;
- reusing the same snapshot ID and upstream puzzle path with different puzzle bytes is likewise rejected.

This path acquires source facts only. Canonical `PuzzleArtifact` materialization, simulation/verification, normalized puzzle generation, and release inclusion remain separate downstream responsibilities.
