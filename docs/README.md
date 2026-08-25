# Documentation map

This directory contains durable corpus contracts, strategic sequencing, source/acquisition notes, and verification/publication guidance.

Live execution status belongs in GitHub issues and pull requests. Repository documentation should not need edits merely because an issue or pull request is opened, merged, closed, reopened, or restacked. Implementation history belongs in Git and pull-request history rather than a parallel documentation archive.

## Durable documents

| Document | Role |
| --- | --- |
| [`CLEANUP.md`](CLEANUP.md) | Small, understood maintenance that is safe to pick up opportunistically and does not require independent coordination. |
| [`TODO.md`](TODO.md) | Stable dependency/concurrency topology and work-packet boundaries. It deliberately contains no live execution state. |
| [`roadmap.md`](roadmap.md) | Strategic milestones, dependency order, packet boundaries, and sequencing rationale. |
| [`dataset-spec.md`](dataset-spec.md) | Canonical data model, invariants, provenance, verification, normalization, reproducibility, and release acceptance criteria. |
| [`verification.md`](verification.md) | Pinned `libverify` implementation identity, native boundary, canonical success/failure semantics, metric recomputation, and deterministic artifact-to-verification materialization. |
| [`puzzle-serialization.md`](puzzle-serialization.md) | V1 versioned deterministic model-oriented serialization over canonical normalized puzzle records. |
| [`benchmark-protocol.md`](benchmark-protocol.md) | Benchmark protocol boundary, Solve-first evaluation design, attempt profiles, scoring/reporting, contamination guidance, and result requirements. |
| [`solution-views.md`](solution-views.md) | V1 deterministic all-verified, vanilla-constructible, and record-eligible research-view contract. |
| [`hugging-face-export.md`](hugging-face-export.md) | Loading-script-free Hugging Face/Parquet publication contract. |
| [`source-inventory.md`](source-inventory.md) | Frozen base-game collection membership, pinned source evidence, provenance roles, and rights boundaries. |
| [`leaderboard-bot-acquisition.md`](leaderboard-bot-acquisition.md) | Pinned leaderboard-bot collection-evidence acquisition and fail-closed reconciliation contract. |
| [`molecule-db-acquisition.md`](molecule-db-acquisition.md) | Pinned molecule-db acquisition and semantic-evidence contract. |
| [`official-puzzle-acquisition.md`](official-puzzle-acquisition.md) | Explicit local official-puzzle byte acquisition, provenance, cache identity, and rights contract. |
| [`official-game-extraction.md`](official-game-extraction.md) | Local extraction path for exact official puzzle artifacts from an operator-owned game installation. |

## Authority and history

For implemented behavior, committed schemas, collection manifests, configuration, code, and tests are authoritative. The focused documents above describe durable contracts and intended boundaries. GitHub issues and pull requests own live execution state, review discussion, and acceptance evidence.

Generated release artifacts, coverage reports, manifests, and benchmark reports are projections. Regenerate them with deterministic repository software rather than maintaining copies as documentation.

Historical implementation plans, agent choreography, RED/GREEN transcripts, and superseded design snapshots are intentionally not retained in the durable documentation tree. Git and pull-request history preserve that record without making old execution context look like current architecture.
