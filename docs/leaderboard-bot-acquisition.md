# Leaderboard-bot acquisition

The `leaderboard-bot` source adapter acquires pinned Opus Magnum catalog-model evidence from `F43nd1r/zachtronics-leaderboard-bot` at revision `ca40dee95da584270eb3be1c4b74e2be63afa7e6`.

The frozen repository collection remains authoritative for membership. This adapter does not import an upstream collection as a second catalog. It acquires source evidence and requires it to agree with the committed collection.

## Acquired evidence

The adapter reuses the shared streaming GitHub tarball reader and `ContentAddressedCache`. It filters the archive before reading member payloads and retains exactly these model files:

- `OmPuzzle.kt`
- `OmGroup.kt`
- `OmCollection.kt`
- `OmType.kt`

Their exact bytes are cached with the pinned source revision before semantic reconciliation. This preserves the evidence packet when reconciliation later fails. No extracted-repository snapshot, second cache, or generated source index is introduced.

Submitted solution payloads are not part of this adapter. `om-leaderboard` remains the source-specific acquisition path for leaderboard solution and JSON payloads.

## Reconciliation contract

For every row in the frozen collection, the adapter resolves the pinned upstream puzzle model by game puzzle ID and requires exact agreement for:

- leaderboard key;
- display name;
- collection-derived kind;
- canonical group;
- puzzle type.

The adapter also validates model references and rejects duplicate upstream game puzzle IDs or leaderboard keys. Missing required model files, malformed model data, unknown group/type references, missing collection identities, or any disagreement with committed collection facts fail closed.

Successful reconciliation preserves repository inventory order. The pinned upstream contract test fetches the exact revision and requires all 166 rows of `base-game-2026-06-16` to reconcile.

## Rights and authority boundary

The upstream repository is Apache-2.0 licensed, but the cache records these source-evidence files conservatively as `local_fetch_only`; this does not establish rights for unrelated game content or submitted solutions.

Acquisition coverage means that pinned upstream identity/group/type evidence reconciled with the repository collection. It does not make leaderboard-bot the authority for collection membership, puzzle semantics, solution validity, or verifier metrics.
