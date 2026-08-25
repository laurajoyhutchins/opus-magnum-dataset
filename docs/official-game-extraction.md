# Official game puzzle extraction

WP-12 requires verifier-usable exact `.puzzle` artifacts for every frozen puzzle. The installed game does not expose its built-in puzzles as loose files, so this repository includes a local extractor that asks the patched game runtime to serialize the vanilla `Puzzle` objects it already loaded.

This is an acquisition/provenance workflow only. It does not make `.puzzle` bytes the semantic authority for the corpus, does not reconstruct official bytes from decoded semantics, and does not change redistribution rights. Extracted bytes, the prepared source root, and the content cache remain local operator inputs and must not be committed.

## Boundary

The workflow has two deterministic stages:

1. `tools/official-puzzle-extractor/mod` runs inside a locally owned Opus Magnum installation under Quintessential. During `LoadPuzzleContent`, before Quintessential layers custom campaigns or journals on top of the vanilla game state, it walks the vanilla Campaign/Journal object graph, finds loaded `Puzzle` objects, and invokes the game's patched vanilla `Puzzle.method_1248` writer. Output files are named by SHA-256 and published to a fresh directory only after the dump succeeds.
2. `prepare_official_source_root()` reads only each dumped artifact's format/version and embedded puzzle-name header. It reconciles those names against the frozen collection's authoritative `leaderboard_key`, requires exactly one byte payload for every collection puzzle, copies the bytes unchanged to stable `puzzles/<game_puzzle_id>.puzzle` paths, and generates the existing `official-puzzles.toml` contract atomically.

Unknown valid game puzzles such as tutorials may appear in the runtime dump and are ignored during reconciliation. Missing collection coverage, conflicting bytes for one collection puzzle, malformed dumped files, unsafe paths, or an existing/overlapping destination fail closed.

## Build and install the extractor

Use a Quintessential-patched copy of the exact game snapshot you intend to record. The patched directory must contain `ModdedLightning.exe`.

In PowerShell from this repository:

```powershell
$env:OPUS_MAGNUM_DIR = "C:\Program Files (x86)\Steam\steamapps\common\Opus Magnum"
dotnet build .\tools\official-puzzle-extractor\mod\OfficialPuzzleExtractor\OfficialPuzzleExtractor.csproj -c Release

$mod = Join-Path $env:OPUS_MAGNUM_DIR "Mods\OpusCorpusOfficialPuzzleExtractor"
if (Test-Path $mod) { throw "Extractor mod destination already exists: $mod" }
Copy-Item .\tools\official-puzzle-extractor\mod $mod -Recurse
```

The project targets `net452`, matching established Quintessential code-mod practice, and resolves its only game reference from `OPUS_MAGNUM_DIR`/`OpusMagnumDir`. No game binaries are vendored in this repository.

## Produce a fresh runtime dump

Choose a path that does not exist. The extractor deliberately refuses to overwrite or merge a previous dump.

```powershell
$env:OPUS_CORPUS_PUZZLE_DUMP = "C:\temp\opus-magnum-official-puzzles"
& (Join-Path $env:OPUS_MAGNUM_DIR "ModdedLightning.exe")
```

Once the game reaches normal startup, the dump directory has already been promoted. Exit the game, then unset the trigger so later launches do not attempt another export:

```powershell
Remove-Item Env:OPUS_CORPUS_PUZZLE_DUMP
```

The raw dump contains content-addressed `.puzzle` files only. A failed extraction leaves no destination directory.

## Reconcile the dump to the frozen collection

Use a fresh output path and a snapshot identifier that records the exact local game build/depot manifest used for extraction. The identifier is provenance supplied by the operator; it is not inferred from mutable local installation metadata.

```bash
uv run python tools/official-puzzle-extractor/prepare.py \
  --collection collections/base-game-2026-06-16.toml \
  --dump /path/to/opus-magnum-official-puzzles \
  --output /path/to/official-game-source \
  --snapshot-id steam-558991-<exact-manifest-id>
```

Preparation succeeds only if all 166 frozen collection rows are reconciled. The resulting directory contains `official-puzzles.toml` plus stable `puzzles/P*.puzzle` paths and is directly consumable by the existing adapter:

```bash
uv run opus-corpus fetch base-game-2026-06-16 \
  --source official-game \
  --source-root /path/to/official-game-source \
  --cache .cache
```

The adapter records the manifest and exact puzzle payloads with `rights_status = "local_fetch_only"`. From that point onward, WP-12 consumes the normal pinned content cache; the offline release command does not reach back into the game installation.

## What this deliberately does not do

- It does not download Opus Magnum, Steam depots, or proprietary game content.
- It does not commit, publish, or redistribute extracted `.puzzle` payloads.
- It does not synthesize an official binary from molecule/semantic data.
- It does not implement the semantic `.puzzle` decoder tracked separately by issue #61; the preparation step reads only the transport header required to identify a dumped artifact.
- It does not create another cache or artifact authority. The prepared directory is only an explicit local source for the existing `official-game` adapter.
