# Source inventory

Status: frozen collection membership; ingestion coverage may improve without changing membership.

## Collection

`base-game-2026-06-16` contains 166 scored, built-in synthesis puzzles available in the base game by 2026-06-16:

- Campaign chapters 1–5: 36
- Appendix production puzzles: 11
- Journal XCIX, Issues I–XII: 59
- Journal CVIII, Issues I–XII: 60

The collection excludes tutorial micro-lessons, De Re Metallica, custom and Workshop puzzles, and tournament material.

Membership is frozen from the pinned Opus Magnum puzzle/group/collection model in `F43nd1r/zachtronics-leaderboard-bot` at revision `ca40dee95da584270eb3be1c4b74e2be63afa7e6`. The final Journal CVIII issue was published on 2026-06-16, completing 24 Journal issues across Journal XCIX and Journal CVIII.

The authoritative repository inventory is `collections/base-game-2026-06-16.csv`; source repositories are evidence and acquisition inputs, not alternate membership authorities.

## Source matrix

| Source | Pinned revision | Confirmed collection coverage | Primary role | Raw payload policy |
| --- | --- | ---: | --- | --- |
| `F43nd1r/zachtronics-leaderboard-bot` | `ca40dee95da584270eb3be1c4b74e2be63afa7e6` | 166/166 identities | Membership evidence, upstream identifiers, grouping, record/frontier metadata | Do not assume executable solution payload redistribution |
| `ianh/omsim` | `758f4a4b4c9e24f50294801da774a0960c922bab` | 36/36 campaign synthesis puzzle fixtures acquired; additional historical Journal test fixtures are not counted as catalog coverage | Verification authority and campaign puzzle transcription source | Puzzle fixture redistribution rights unresolved; default `local_fetch_only` |
| `F43nd1r/om-archive` | `44006a0eeb0051337640443d1b0576ea24c983f6` | 91/166 puzzles with 2,302 acquired solution candidates | Historical human solution archive | No repository-wide content license observed; default `local_fetch_only` |
| `F43nd1r/om-leaderboard` | `0cfd371ef66cf94eac3f7a7a06bc9ab959495576` | 166/166 puzzles with 15,525 acquired solution candidates and 15,521 JSON metadata records; verification pending | Current human solution payloads plus score, data-path, display-link, and modification metadata | Repository declares Unlicense, but applicability to submitted player solution bytes is not assumed; default raw `.solution` policy remains `local_fetch_only` pending source-specific rights evidence |
| `fenhl/molecule-db` | `6f3cd8068428ef96ac6426d092c3523da359ec76` | Current official-puzzle semantic data including Journal CVIII; exact official `.puzzle` byte coverage is not claimed | Independent problem-definition evidence for puzzle identity, collection association, and reagent/product molecule topology | Relevant source files are MIT-licensed; this does not establish redistribution rights for official game bytes |

Coverage numbers describe confirmed puzzle-level source coverage, not a claim that every source artifact is valid or redistributable. Candidate and metadata-record counts are pinned-revision acquisition facts, not verifier-success counts.

## `om-archive` coverage

Mechanical acquisition from the pinned revision, mapped against the frozen collection manifest, finds 2,302 `.solution` candidates across 91 collection puzzles:

- Campaign: 36/36 puzzles, including `P007` / Stabilized Water.
- Appendix: 11/11 puzzles.
- Journal XCIX Issues I–IX: 44/44 puzzles from that historical issue range.

This totals 91 collection puzzles. The acquisition result supersedes the earlier prose inventory that incorrectly described Stabilized Water as absent.

Relative to the frozen 166-puzzle collection, 75 puzzles are outside the archive's acquired candidate coverage:

- Journal XCIX Issues X–XII: 15
- Journal CVIII Issues I–XII: 60

Those 75 are a derived comparison between the frozen collection and acquired `om-archive` facts, not a source definition. Independent `om-leaderboard` acquisition contains executable candidates for all 75, as well as overlapping candidates for the 91 puzzles represented by `om-archive`. Verification remains pending until acquired payloads are paired with authoritative puzzle definitions and passed through the pinned verifier.

## Current leaderboard solution acquisition

The pinned `F43nd1r/om-leaderboard` revision contains collection-matching material across all campaign, appendix, Journal XCIX, and Journal CVIII groups. Its adapter is source-independent: it maps every frozen collection row to the corresponding leaderboard directory using only the source layout plus the canonical group and leaderboard key. It does not encode or consult `om-archive` coverage.

A live acquisition against revision `0cfd371ef66cf94eac3f7a7a06bc9ab959495576` produced 15,525 `.solution` candidates across all 166 collection puzzles and 15,521 JSON metadata records. Overlapping source facts are retained rather than suppressed. Among the 75 puzzles that are derived gaps in `om-archive`, the pinned-source diagnostic identified four `JOURNAL_X/BEAUTY_SALVE` solution candidates with no same-basename JSON and no JSON `dataPath` reference to them; those executable source facts remain valid acquisition candidates.

The `.json` records expose claimed score fields and source associations such as `dataPath`. These claims are observations only. Acquisition hashes and caches raw JSON bytes without interpreting the claims as verified metrics. JSON records are retained even when no same-basename `.solution` exists, because source-fact preservation is independent of later pairing and verification.

The implemented acquisition contract:

1. Derives source directories for all 166 frozen collection identities from canonical group and leaderboard keys using the leaderboard repository layout.
2. Downloads the exact pinned repository tarball and enumerates it deterministically.
3. Caches every `.solution` and `.json` file directly under those collection-matching puzzle directories as `local_fetch_only` source bytes.
4. Preserves overlapping facts also present in `om-archive` and preserves unpaired JSON metadata rather than treating either as redundant.
5. Ignores source material outside the frozen collection.
6. Reports source-local candidate and puzzle coverage without imposing completeness assumptions derived from another adapter.

Archive gaps, cross-source overlaps, exact-byte deduplication, and release completeness are downstream derived state. A releasable build must still fail if the collection lacks required verifier-successful coverage; the acquisition adapter itself does not turn another source's coverage into its own contract.

Verification is the next stage: acquired candidates still need authoritative puzzle artifacts, pinned `omsim` execution, recomputed metrics, canonical artifact/observation materialization, and release integration.

## Problem-definition acquisition

Exact official game `.puzzle` bytes and normalized semantic puzzle facts are separate artifact classes.

`omsim` remains the campaign transcription source and already includes `P007` / Stabilized Water. It does not provide a complete current Journal puzzle fixture tree.

For the Journal puzzles that were previously outside confirmed puzzle-byte coverage, `fenhl/molecule-db` provides an independent semantic source: its puzzle model associates official puzzle identities with collections, and its molecule table records reagent/product molecule topology as atoms and bonds. This source can support normalized problem-definition generation and cross-checking, but it must not be treated as proof of exact official `.puzzle` byte identity or of every game-level field such as allowed-part encoding.

Therefore:

- Use the pinned leaderboard-bot model for canonical puzzle identity, upstream ID, group, and puzzle type.
- Use the pinned molecule database as independent evidence for reagent/product semantic structure.
- Use locally acquired official puzzle bytes when exact binary fidelity is required, keeping those bytes `local_fetch_only` unless redistribution rights are established.
- Validate any generated normalized Journal problem representation by pairing it with at least one independently acquired solution and running the pinned verifier. Generation must fail rather than silently fill unknown game fields.

## `omsim` coverage

The pinned `omsim` revision is the planned executable verification authority and the implemented campaign transcription source. Mechanical acquisition against revision `758f4a4b4c9e24f50294801da774a0960c922bab` yields 36 `.puzzle` candidates across all 36 scored campaign synthesis puzzles.

The acquisition contract maps only `test/puzzle/campaign/**/<game_puzzle_id>.puzzle` files to frozen campaign identities, caches the exact matching bytes through the shared content-addressed cache, and records them as `local_fetch_only`. Historical Journal fixtures and non-collection puzzle files are deliberately ignored. If more than one campaign fixture claims the same game puzzle ID, acquisition fails before mutating the cache. Repeating acquisition from the same pinned source is idempotent and leaves receipt/object bytes unchanged.

The fixture tree also contains some historical Journal fixtures, but it is not a complete current base-game catalog and is therefore not used to determine collection membership or to claim Journal coverage.

The verifier implementation and the puzzle fixture payloads have separate rights questions. The software's permissive/public-domain-style grant does not itself establish redistribution rights for commercial game content represented by puzzle fixtures.

## Source-specific rights evidence

[`../RIGHTS.md`](../RIGHTS.md) defines the repository-wide license scope, the meanings of `rights_status`, and the fail-closed redistribution policy. This section records evidence specific to the pinned sources; it is not a second policy authority.

- Official game puzzle bytes have no independently established redistribution grant in this corpus and remain `local_fetch_only`.
- No repository-wide content license has been observed for `om-archive`; its solution payloads remain `local_fetch_only`.
- `om-leaderboard` declares the Unlicense at its repository root, but the corpus does not assume that declaration conclusively covers every player-submitted solution payload; raw `.solution` artifacts therefore remain `local_fetch_only` pending source-specific evidence.
- Leaderboard metadata is retained as provenance-bearing factual observation material, with claimed metrics kept distinct from verifier-derived metrics.
- Relevant `molecule-db` source files are MIT-licensed, but that source license does not relicense official game content represented by derived semantic facts.

Source-specific evidence can become more complete without changing the repository-wide policy. A later source or clearer grant may justify a different `rights_status` for a particular artifact without broadening rights for unrelated artifacts.

## Source precedence

Sources do not overwrite one another.

If multiple sources yield the same raw artifact hash, the corpus stores one artifact with multiple observations. If two sources disagree about a claimed score or identifier, both claims are retained and the pinned verifier result remains separate. Source metadata never silently replaces verified metrics.

## Freeze rule

Collection membership is frozen because the complete scored built-in puzzle identity set is known and recorded independently of acquisition coverage.

Improving solution coverage, adding observations, finding newer archives, changing a source adapter, or discovering additional valid solutions does not mutate the collection. A new collection manifest is required only when the intended puzzle membership itself changes.
