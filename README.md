# Opus Magnum Dataset

A reproducible, provenance-preserving corpus of Opus Magnum puzzles and solutions, designed for verification, benchmarking, search, and machine-learning research.

This repository is the **factory and specification**, not a hand-maintained dataset. Authoritative source facts are ingested from pinned upstream sources, verified deterministically, and materialized into generated dataset artifacts.

## Current phase

The collection contract and generic release shell are implemented. The repository can validate the frozen collection and can build, validate, stage, and publish a four-config Hugging Face-compatible release from canonical JSONL inputs.

Source acquisition includes pinned community/archive inputs, pinned `omsim` campaign puzzle definitions, molecule-db semantic evidence, and an explicit local path for exact official `.puzzle` bytes. Canonical exact-byte puzzle/solution artifact materialization, deterministic `omsim` / `libverify` verification, and deterministic `.solution` parsing/normalization are implemented. The active downstream slice is release materialization from those canonical entities; complete frozen-collection release coverage follows after that. The committed `fixtures/tiny-corpus/` exists to prove the release factory before the production materialization path is connected end to end. See [`docs/TODO.md`](docs/TODO.md) for the current packet/dependency snapshot.

## Implemented release shell

The `opus-corpus` CLI owns collection validation, source acquisition, and generated releases:

```text
opus-corpus collections validate [manifest]
opus-corpus fetch <collection> --source <source> --cache <path> [--source-root <path>]
opus-corpus release build <collection> --input <path> --output <path> --payload-policy metadata-only [--coverage-policy complete|subset]
opus-corpus release validate <collection> --output <path>
opus-corpus release stage <collection> --output <path> --destination <path>
opus-corpus release publish <collection> --output <path>
```

`--source-root` is required only for the `official-game` adapter. That adapter consumes a strict local `official-puzzles.toml`, preserves the manifest itself as an immutable source fact, and stores exact local puzzle bytes with `local_fetch_only` rights through the shared content-addressed cache.

A release materializes four independently loadable configs: `puzzles`, `solutions`, `observations`, and `normalized`. Collection IDs become immutable Hugging Face split names, so `base-game-2026-06-16` maps to `base_game_2026_06_16` rather than a generic `train` split.

Generated release state includes deterministic logical-record hashes, a release manifest, Parquet output hashes, and a generated dataset card. Hugging Face is a downstream distribution surface; GitHub repository facts and canonical build inputs remain authoritative.

Coverage policy is explicit build state. `complete` is the default and requires the exact frozen collection plus at least one verified solution for every puzzle. `subset` is an explicit development/fixture mode and is recorded in the release manifest. Human-editable release metadata cannot relax the build policy. Per-puzzle candidate, verified, rejected, and coverage-state facts are derived into `release_metadata.coverage.by_puzzle` in the generated manifest.

## Payload policy

Every build selects an explicit payload policy:

- `metadata-only` requires raw puzzle and solution byte fields to be null.
- `include-permitted` allows raw bytes only for rows whose `rights_status` is exactly `redistributable`.

The release validator reapplies the payload policy after reading generated Parquet so staging cannot bypass rights checks.

## License and rights

The project's repository-authored material is licensed under the [MIT License](LICENSE). That repository license does not grant blanket rights to official game content, player-authored solutions, or other third-party source artifacts.

[`RIGHTS.md`](RIGHTS.md) is the repository-wide authority for license scope and redistribution policy. Source-specific rights evidence remains documented with provenance, and generated releases must preserve per-artifact rights rather than infer a dataset license from the repository's MIT license.

## Development

Python 3.12 is the supported runtime. From the committed lockfile environment:

```bash
uv sync --all-extras --locked
uv run ruff check .
uv run pytest -q
uv run opus-corpus collections validate
```

Tests marked `upstream` require live access to exact pinned external revisions and are excluded from the ordinary hermetic pytest suite. CI runs them explicitly with:

```bash
uv run pytest -q -o addopts= -m upstream
```

The upstream verification contract builds `libverify.so` from the exact pinned `omsim` revision and exercises a real puzzle/solution pair through the production ctypes adapter. Runtime verification itself consumes an explicitly supplied shared-library path and records the exact binary SHA-256 in canonical verifier identity; it does not create a second source cache or verifier object store.

Canonical JSON Schemas are repository-authored package resources under `src/opus_corpus/schemas/`. Collection and release validation resolve them through `opus_corpus.schema_resources`; `corpus.toml` does not configure a schema directory. Source/editable execution and installed-wheel execution therefore consume the same schema bytes, while release manifests retain stable logical `schemas/<name>` paths and hashes instead of checkout-specific filesystem paths.

To exercise the tiny release factory locally, opt into subset coverage explicitly:

```bash
uv run opus-corpus release build base-game-2026-06-16 \
  --input fixtures/tiny-corpus \
  --output .tmp-release \
  --payload-policy metadata-only \
  --coverage-policy subset
uv run opus-corpus release validate base-game-2026-06-16 --output .tmp-release
uv run opus-corpus release stage base-game-2026-06-16 \
  --output .tmp-release \
  --destination .tmp-stage
```

Generated release directories are projections and should not be treated as repository authority.

## Design principles

- Source bytes are immutable facts.
- Every published row is traceable to provenance.
- Claimed metrics are not trusted; metrics are recomputed by a pinned verifier.
- Collection membership is explicit and versioned.
- Derived views are generated by software, never manually curated.
- Hugging Face is a first-class publication target, not the internal source of truth.
- Redistribution of raw puzzle or solution bytes is controlled independently from metadata publication.
- Exact-byte deduplication is safe; semantic-equivalence deduplication is deferred until separately specified.

## Documents

- [`RIGHTS.md`](RIGHTS.md) — repository license scope and authoritative redistribution policy.
- [`docs/README.md`](docs/README.md) — map of current contracts, planning documents, and dated historical design notes.
- [`docs/TODO.md`](docs/TODO.md) — dependency/concurrency work graph and current landed/ready/blocked implementation snapshot.
- [`docs/roadmap.md`](docs/roadmap.md) — dependency-ordered path from the current corpus factory to the first complete release and later research expansion.
- [`docs/dataset-spec.md`](docs/dataset-spec.md) — canonical corpus model, invariants, validation, provenance, reproducibility, and release acceptance criteria.
- [`docs/verification.md`](docs/verification.md) — pinned `libverify` identity, native boundary, canonical failure semantics, metric recomputation, and deterministic artifact-to-verification materialization.
- [`docs/benchmark-protocol.md`](docs/benchmark-protocol.md) — versioned benchmark boundary, Solve-first evaluation protocol, metrics, attempt policies, contamination guidance, and result requirements.
- [`docs/hugging-face-export.md`](docs/hugging-face-export.md) — loading-script-free Hugging Face / Parquet publication contract.
- [`docs/source-inventory.md`](docs/source-inventory.md) — frozen collection coverage and source-specific rights evidence.
- [`docs/molecule-db-acquisition.md`](docs/molecule-db-acquisition.md) — pinned semantic-source evidence, reconciliation, cache ordering, and upstream test contract.
- [`docs/official-puzzle-acquisition.md`](docs/official-puzzle-acquisition.md) — explicit local official-byte manifest, provenance, cache identity, and rights contract.

## Source classes

Implemented acquisition and verification paths include:

- `om-archive` for historical community solutions;
- Zachtronics Leaderboards for current record/frontier observations;
- `omsim` for pinned campaign puzzle-definition acquisition;
- molecule-db for semantic puzzle evidence without claiming exact official byte identity;
- `official-game` for explicitly mapped local official `.puzzle` bytes with `local_fetch_only` rights;
- pinned `omsim` / `libverify` execution for deterministic canonical verification and metric recomputation.

Planned source work includes clearly identified machine-generated baselines such as OpusSolver output.

Source adapters do not define the dataset schema. They translate upstream facts into the canonical model.

## Non-goals for v1

- A database service.
- A custom simulator.
- Agent-maintained indexes or projections.
- Semantic deduplication of equivalent machines.
- A hand-curated folder of “best” solutions.
- Treating leaderboard metadata as executable-solution truth.
- Treating a mutable notion of “current base game” as a collection definition.
