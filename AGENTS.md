# AGENTS.md

These instructions apply to the entire repository unless a deeper `AGENTS.md` overrides them for a narrower subtree.

## Mission

This repository is the factory and specification for a reproducible, provenance-preserving Opus Magnum corpus. Build deterministic software that turns immutable, pinned source facts into canonical entities and generated release artifacts. Do not turn the repository into a hand-maintained dataset, evidence ledger, or collection of parallel authorities.

## Read before changing code

Start with:

1. `README.md` for the current repository shape and supported commands.
2. `docs/TODO.md` for the dependency graph, packet ownership boundaries, and current static work map.
3. `docs/dataset-spec.md` for canonical entities, provenance rules, and source-fact/derived-state boundaries.
4. The focused design/source document for the subsystem you are changing.

Inspect the implementation and recent relevant PRs before proposing a new abstraction. Consume landed interfaces instead of recreating them.

## Authority and live execution

- GitHub repository contents are authoritative for code, schemas, collection definitions, tests, and durable documentation.
- GitHub issues and pull requests are the repository execution record.
- `docs/TODO.md` is a dependency/concurrency map and planning aid. It is not live claim state and must not become an assignee ledger.
- The **Hatchable Portfolio Control Plane** is the sole live orchestration authority. The historical Agent Execution Control Plane is obsolete and must not be revived or treated as a fallback.
- Before implementation, claim exactly one executable work item with `work.claim`. Settle it with `work.settle` only after fresh verification evidence satisfies its acceptance criteria.
- If the Portfolio Control Plane is unavailable in the current environment, do not emulate claim or settlement state in GitHub, Linear, comments, or `docs/TODO.md`. Report the limitation instead of inventing a second control surface.
- Linear, when present, is only a thin projection of currently executable work. Do not use it as a repository, evidence store, or historical archive.

## Control-plane primitives

Before adding orchestration machinery, check whether an existing Portfolio Control Plane primitive already provides the required semantics. Important primitives include:

- `work.claim`
- `work.settle`
- `github.apply_changeset`
- `github.review_packet`
- `github.delete_branch`
- `github.required_checks.ensure`
- `portfolio.reconcile_work_surface`
- `object.capture`
- `object.get_verified`

Use higher-level control-plane commands when atomicity, idempotency, conditional mutation, evidence, or protocol semantics justify them. Do not recreate ordinary GitHub functionality inside the control plane without a comparable reason.

## Concurrency and ownership

- Work on one claimed packet or issue at a time.
- Respect the ownership boundaries and dependency edges in `docs/TODO.md`.
- Do not concurrently modify a surface owned by another active item unless the work graph explicitly allows it.
- Branch from the settled dependency base declared by the work graph. Use stacked PRs only when there is a real dependency edge or an explicit collision-avoidance sequence.
- Own the capability, not neighboring machinery. If the task requires changing another packet's public contract, split or restack the work rather than silently widening scope.
- If two items unexpectedly require the same implementation surface, fix the graph or extract the smallest shared primitive before continuing. Do not let two agents mutate the same boundary independently.

## One authoritative path

Prefer deletion, consolidation, and deterministic derivation over parallel mechanisms or compatibility layers.

Do not create a second authority for any existing concern, including:

- exact-byte content storage;
- source acquisition receipts;
- canonical artifact identity;
- canonical verification results;
- normalized record identity;
- release materialization;
- coverage or verification counts;
- generated manifests, cards, or indexes.

Use the established shared primitives. If an existing path is inadequate, improve or replace it explicitly rather than adding a competing path beside it.

## Agent versus software

Apply this test repeatedly:

> What are we prompting agents to do that deterministic software could do instead?

Move repeated bookkeeping, reconciliation, counting, validation, materialization, state derivation, and known recovery choreography into typed deterministic software. Use reasoning agents for judgment, research, synthesis, design, and novel implementation.

If a recurring orchestration failure is understood, prefer a machine-readable state and deterministic recovery path over another prompt instruction.

## Data and provenance invariants

- Source bytes and pinned upstream facts are immutable inputs.
- Every published artifact or row must remain traceable to provenance.
- Exact byte identity is the v1 deduplication boundary unless a separately specified semantic-equivalence layer says otherwise.
- Source-declared metrics are observations, not verified truth. Recompute authoritative metrics with the pinned verifier.
- Preserve disagreement between source claims and deterministic verification rather than overwriting either fact.
- Derived state must be reproducible from authoritative source facts plus pinned software/configuration.
- Never hand-maintain generated coverage, verification counts, release manifests, dataset cards, indexes, or other derivable projections.
- Treat Hugging Face and other publication surfaces as downstream distributions, not repository authority.
- Keep rights and redistribution policy explicit. Never broaden raw-byte publication rights by inference.

## Fail closed

Reject ambiguous or unsafe states rather than guessing. In particular, fail closed on:

- source mutation or corrupt cached objects;
- ambiguous puzzle or artifact mapping;
- incompatible formats or unsupported manifest versions;
- provenance or identity conflicts;
- unsafe filesystem paths, traversal, or staging overlap;
- rights-policy violations;
- incomplete required coverage when complete coverage is requested.

Do not repair these cases by silently dropping records, weakening policy, or inserting hand-authored exceptions.

## Repository shape

- `src/opus_corpus/`: implementation.
- `tests/`: hermetic tests plus explicitly marked pinned-upstream contracts.
- `collections/`: immutable collection definitions.
- `fixtures/tiny-corpus/`: small deterministic release-factory fixture.
- `docs/`: durable specifications, source contracts, roadmap, and work graph.
- `.github/workflows/`: validation and publication automation.

Generated release directories are projections. Do not treat them as source-of-truth repository state.

## Implementation discipline

- Prefer small, typed interfaces with one clear owner.
- Keep source adapters responsible for translating upstream facts, not redefining canonical schemas or verification semantics.
- Preserve deterministic ordering and identity. Tests should cover order independence and local-root independence where relevant.
- Keep acquisition, parsing, verification, normalization, materialization, and publication boundaries separate unless an established interface intentionally joins them.
- Avoid repository-layout assumptions in installed-package behavior.
- Use public behavior in regression tests when practical. Do not couple tests to private helpers merely to make determinism easier to assert.
- For behavior changes and bug fixes, use focused red/green tests and then run the relevant broader suite. Documentation-only changes do not need artificial tests.
- Do not perform unrelated refactors while touching a subsystem.

## Development commands

Python 3.12 and the committed lockfile define the development environment.

```bash
uv sync --all-extras --locked
uv run ruff check .
uv run pytest -q
uv run pytest -q -o addopts= -m upstream
uv run opus-corpus collections validate
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

The ordinary pytest suite is hermetic. Tests marked `upstream` intentionally require access to exact pinned external revisions. If the environment cannot run an upstream check, state that explicitly; never report it as passing without evidence.

Run the smallest relevant checks during development, then fresh validation appropriate to the changed surface before settlement or merge. For changes that can affect the release boundary, mirror the complete CI validation sequence above.

## Pull requests and settlement

A PR should make concurrent review easy. State:

- the claimed packet or issue and its settled dependencies;
- the capability and implementation surface owned by the PR;
- explicit non-goals;
- any dependency or stacking relationship;
- fresh verification evidence, including red/green regression evidence when applicable.

Keep PRs narrow enough that another worker can safely operate on an independent packet. Do not mark work settled because code exists or a branch is mergeable. Settle only after the required evidence is fresh and the landed state satisfies the work item's acceptance criteria.

## Documentation maintenance

Update durable documentation when a contract, command, invariant, dependency, or architectural boundary changes. Do not copy fast-moving live status into multiple files.

In particular:

- keep `README.md` focused on the current usable repository shape;
- keep `docs/TODO.md` as the dependency/concurrency map rather than a live control plane;
- keep detailed subsystem contracts in focused documents;
- prefer links to authoritative facts over duplicated prose that agents must later reconcile.

When terminology and implementation disagree, resolve the discrepancy. Names should describe the system that actually exists.
