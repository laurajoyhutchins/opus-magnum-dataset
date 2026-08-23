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

Those 76 are source-discovery gaps, not collection-membership gaps. They may be covered by newer archives, leaderboard-attached artifacts, generated baselines, or other permitted sources without changing `base-game-2026-06-16`.

## `omsim` coverage

`omsim` is the planned executable verification authority. Its current test fixture tree contains transcriptions for all 36 scored campaign synthesis puzzles. It also contains some historical Journal fixtures, but the fixture tree is not a complete current base-game catalog and is therefore not used to determine collection membership.

The verifier implementation and the puzzle fixture payloads have separate rights questions. The software's permissive/public-domain-style grant does not itself establish redistribution rights for commercial game content represented by puzzle fixtures.

## Rights and redistribution policy

This project records rights status per source and per artifact class. Until source-specific permission or another clear basis is established:

- Official game puzzle bytes are `local-fetch-only`.
- `om-archive` solution bytes are `local-fetch-only`.
- Leaderboard metadata may be observed and hashed, but executable solution payload availability and redistribution are not assumed.
- Hugging Face exports must omit raw `puzzle_bytes` and `solution_bytes` for artifacts whose redistribution status is unresolved.
- Rights status is evidence, not a global repository switch. A later source may permit payload publication without changing the policy for other sources.

This document is a technical provenance policy, not a legal determination.

## Source precedence

Sources do not overwrite one another.

If multiple sources yield the same raw artifact hash, the corpus stores one artifact with multiple observations. If two sources disagree about a claimed score or identifier, both claims are retained and the pinned verifier result remains separate. Source metadata never silently replaces verified metrics.

## Freeze rule

Collection membership is frozen because the complete scored built-in puzzle identity set is known and recorded independently of acquisition coverage.

Improving solution coverage, adding observations, finding newer archives, changing a source adapter, or discovering additional valid solutions does not mutate the collection. A new collection manifest is required only when the intended puzzle membership itself changes.
