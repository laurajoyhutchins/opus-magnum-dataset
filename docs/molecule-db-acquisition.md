# Molecule-db semantic acquisition

The `molecule-db` adapter provides pinned semantic puzzle evidence. It is deliberately separate from exact official `.puzzle` byte acquisition and must not be used to claim binary identity or unsupported game-level fields.

This capability is WP-06 in the repository work graph. The original implementation landed in PR #18; PR #27 hardens evidence retention and adds an end-to-end pinned-source contract.

## Pinned source

The adapter reads exactly revision:

```text
fenhl/molecule-db@6f3cd8068428ef96ac6426d092c3523da359ec76
```

Only two upstream files are semantic acquisition inputs:

```text
src/molecules.rs
src/puzzle.rs
```

Their expected SHA-256 digests at the pinned revision are:

```text
src/molecules.rs  09dbca0f67ba16178f98da0f2a94f642e3114f61a0a3d79c434d8411df175a58
src/puzzle.rs     d6fd2f8d99731081f5d76ab47fbd67c2c19f02f73e04cdb1bdd1ad4534096f11
```

The integration contract verifies these hashes before using the files as evidence for the frozen collection.

## Acquisition and evidence retention

Acquisition follows a fail-closed evidence-first order:

1. Download the exact pinned repository tarball.
2. Extract the required semantic source files and reject the source if either is absent.
3. Store both exact source byte payloads in the shared content-addressed cache with `local_fetch_only` rights.
4. Only after the cache receipts exist, parse and reconcile semantic content against the selected collection.
5. Return coverage only when reconciliation succeeds.

Caching precedes semantic interpretation intentionally. If parsing or collection reconciliation fails, the exact upstream bytes and provenance receipts remain available for diagnosis and reproduction instead of disappearing with the failed interpretation.

The adapter does not create a second object store and does not copy unrelated files from the upstream repository into the acquisition cache.

## Semantic model and reconciliation

The adapter parses:

- official puzzle variant, display name, source collection, and game puzzle ID from `src/puzzle.rs`;
- molecule atoms, bonds, reagent/product appearances, and optional names from `src/molecules.rs`.

Collection reconciliation is keyed by the frozen inventory's `game_puzzle_id`. The corpus retains its canonical `puzzle_id`; the molecule database supplies independent semantic evidence rather than defining collection identity.

Parsing fails closed on malformed or ambiguous source structure, including duplicate puzzle variants or game IDs, unbalanced expressions, duplicate atom positions, invalid bond endpoints, empty appearances, zero reagent-and-product appearances, or missing reagent/product evidence for a frozen puzzle.

At the pinned revision, the upstream contract reconciles all 166 rows of `base-game-2026-06-16` in frozen inventory order.

## Exact-byte boundary

Molecule-db semantics are not exact official puzzle bytes. In particular, this adapter does not expose `puzzle_bytes` or `puzzle_sha256` fields and does not substitute generated semantics for the `official-game` exact-byte path.

Downstream materialization may combine independent provenance claims, but exact official-byte identity must originate from an exact-byte source such as the explicit local official acquisition path.

## Test contract

Ordinary pytest runs are hermetic. Tests requiring live pinned external source access use the registered `upstream` marker and are excluded by default.

The normal suite is:

```bash
uv run pytest -q
```

CI additionally executes the pinned-source contract explicitly:

```bash
uv run pytest -q -o addopts= -m upstream
```

The upstream contract downloads the exact pinned revision, verifies both SHA-256 digests above, loads the frozen collection using a repository-relative path, parses the semantic source, and requires all 166 `game_puzzle_id` values to reconcile in inventory order.

Synthetic unit coverage remains responsible for parser edge cases and for the regression that source receipts survive a reconciliation failure. This split keeps routine development and offline testing deterministic while preserving an explicit live check that the repository's pin still matches its documented semantic contract.

## Rights boundary

The cached semantic source files are recorded as `local_fetch_only`. The upstream source license is evidence about the source code itself and does not establish redistribution rights for official Opus Magnum game bytes or independently sourced player solution payloads.
