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
| `ianh/omsim` | `758f4a4b4c9e24f50294801da774a0960c922bab` | 36/36 campaign synthesis puzzle fixtures; additional historical Journal test fixtures are not counted as catalog coverage | Verification authority and campaign puzzle transcription source | Puzzle fixture redistribution rights unresolved; default `local-fetch-only` |
| `F43nd1r/om-archive` | `44006a0eeb0051337640443d1b0576ea24c983f6` | 90/166 puzzle directories | Historical human solution archive | No repository-wide content license observed; default `local-fetch-only` |
| `F43nd1r/om-leaderboard` | `0cfd371ef66cf94eac3f7a7a06bc9ab959495576` | Candidate acquisition source for the 76 puzzles outside `om-archive` coverage; full per-puzzle payload reconciliation is required before claiming verified coverage | Current human solution payloads plus score, data-path, display-link, and modification metadata | Repository declares Unlicense, but applicability to submitted player solution bytes is not assumed; default raw `.solution` policy remains `local-fetch-only` pending source-specific rights evidence |
| `fenhl/molecule-db` | `6f3cd8068428ef96ac6426d092c3523da359ec76` | Current official-puzzle semantic data including Journal CVIII; exact official `.puzzle` byte coverage is not claimed | Independent problem-definition evidence for puzzle identity, collection association, and reagent/product molecule topology | Relevant source files are MIT-licensed; this does not establish redistribution rights for official game bytes |

Coverage numbers describe confirmed puzzle-level source coverage, not the number of solutions and not a claim that every source artifact is valid or redistributable.

## `om-archive` coverage

At the pinned revision, the archive contains solution directories for:

- Campaign: 35/36 puzzles. `P007` / Stabilized Water is absent.
- Appendix: 11/11 puzzles.
- Journal XCIX Issues I–IX: 44/44 puzzles from that historical issue range.

This totals 90 collection puzzles.

Relative to the frozen 166-puzzle collection, 76 puzzles are outside the archive's confirmed directory coverage:

- Stabilized Water (`P007`): 1
- Journal XCIX Issues X–XII: 15
- Journal CVIII Issues I–XII: 60

Those 76 are gaps in `om-archive`, not collection-membership gaps and no longer unknown source locations. The current `om-leaderboard` repository provides candidate acquisition paths for the missing solution classes. They remain unverified until the ingestion adapter mechanically reconciles every expected puzzle key, acquires a raw `.solution`, and validates it against the pinned verifier.

## Current leaderboard solution acquisition

The pinned `F43nd1r/om-leaderboard` revision contains leaderboard directories for Stabilized Water, Journal XCIX Issues X–XII, and Journal CVIII Issues I–XII. Inspected puzzle directories contain paired `.json` observation metadata and `.solution` payloads, including Stabilized Water, Touchstone, and the final Journal CVIII issue.

The `.json` records expose factual score fields and a `dataPath` that points to the corresponding `.solution`. These claims are observations only. The dataset must recompute metrics from the acquired executable payload rather than trusting filenames or JSON score fields.

The ingestion adapter must derive coverage mechanically from the frozen collection manifest. For each puzzle that is outside `om-archive` coverage, it must:

1. Map the canonical puzzle key to its leaderboard group and slug from the pinned puzzle model.
2. Enumerate the pinned `om-leaderboard` puzzle directory.
3. Require at least one `.solution` candidate and retain the adjacent `.json` as a separate source observation when available.
4. Hash raw bytes before parsing.
5. Verify candidate solutions against the pinned puzzle artifact and pinned verifier.
6. Fail closed if an expected puzzle has no executable candidate or no verifier-successful candidate.

This turns the previous discovery problem into deterministic acquisition and verification work.

## Problem-definition acquisition

Exact official game `.puzzle` bytes and normalized semantic puzzle facts are separate artifact classes.

`omsim` remains the campaign transcription source and already includes `P007` / Stabilized Water. It does not provide a complete current Journal puzzle fixture tree.

For the Journal puzzles that were previously outside confirmed puzzle-byte coverage, `fenhl/molecule-db` provides an independent semantic source: its puzzle model associates official puzzle identities with collections, and its molecule table records reagent/product molecule topology as atoms and bonds. This source can support normalized problem-definition generation and cross-checking, but it must not be treated as proof of exact official `.puzzle` byte identity or of every game-level field such as allowed-part encoding.

Therefore:

- Use the pinned leaderboard-bot model for canonical puzzle identity, upstream ID, group, and puzzle type.
- Use the pinned molecule database as independent evidence for reagent/product semantic structure.
- Use locally acquired official puzzle bytes when exact binary fidelity is required, keeping those bytes `local-fetch-only` unless redistribution rights are established.
- Validate any generated normalized Journal problem representation by pairing it with at least one independently acquired solution and running the pinned verifier. Generation must fail rather than silently fill unknown game fields.

## `omsim` coverage

`omsim` is the planned executable verification authority. Its current test fixture tree contains transcriptions for all 36 scored campaign synthesis puzzles. It also contains some historical Journal fixtures, but the fixture tree is not a complete current base-game catalog and is therefore not used to determine collection membership.

The verifier implementation and the puzzle fixture payloads have separate rights questions. The software's permissive/public-domain-style grant does not itself establish redistribution rights for commercial game content represented by puzzle fixtures.

## Rights and redistribution policy

This project records rights status per source and per artifact class. Until source-specific permission or another clear basis is established:

- Official game puzzle bytes are `local-fetch-only`.
- `om-archive` solution bytes are `local-fetch-only`.
- `om-leaderboard` raw solution bytes are `local-fetch-only` unless contribution or submission terms establish that the repository license applies to those payloads. Its root Unlicense declaration is useful evidence but is not, by itself, treated as conclusive provenance for every player-submitted solution.
- Leaderboard metadata may be observed, hashed, and published as provenance-bearing factual observations; claimed metrics remain distinct from verifier-derived metrics.
- MIT-licensed `molecule-db` source may be used as a semantic evidence source subject to its license, but that license does not relicense official game content represented by derived facts.
- Hugging Face exports must omit raw `puzzle_bytes` and `solution_bytes` for artifacts whose redistribution status is unresolved.
- Rights status is evidence, not a global repository switch. A later source may permit payload publication without changing the policy for other sources.

This document is a technical provenance policy, not a legal determination.

## Source precedence

Sources do not overwrite one another.

If multiple sources yield the same raw artifact hash, the corpus stores one artifact with multiple observations. If two sources disagree about a claimed score or identifier, both claims are retained and the pinned verifier result remains separate. Source metadata never silently replaces verified metrics.

## Freeze rule

Collection membership is frozen because the complete scored built-in puzzle identity set is known and recorded independently of acquisition coverage.

Improving solution coverage, adding observations, finding newer archives, changing a source adapter, or discovering additional valid solutions does not mutate the collection. A new collection manifest is required only when the intended puzzle membership itself changes.
