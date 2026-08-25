# AGENTS.md

These instructions apply to the entire repository unless a deeper `AGENTS.md` overrides them.

## Mission

Build a reproducible, provenance-preserving Opus Magnum corpus with deterministic software. Immutable pinned source facts are inputs; canonical entities and release artifacts are derived outputs. Do not create hand-maintained dataset state, duplicate authorities, or parallel implementation paths.

## Read first

Before changing a subsystem, read:

1. `README.md` for repository shape and commands.
2. `docs/TODO.md` for dependency and concurrency boundaries.
3. `docs/dataset-spec.md` for canonical entities and provenance rules.
4. The focused contract or design document for the subsystem.
5. Relevant open issues, pull requests, and landed interfaces.

Prefer using or improving an existing interface over creating another abstraction beside it.

## Authority and work state

- Repository contents are authoritative for code, schemas, collection definitions, tests, and durable documentation.
- GitHub issues and pull requests are the execution record.
- `docs/TODO.md` is a dependency/concurrency map, not a second issue tracker.
- External automation may operate the repository, but repository procedure and correctness must remain understandable from versioned content and ordinary GitHub state.
- Contributors must not need a private control plane, proprietary tracker, or agent-specific runtime to understand or execute repository work.

## Busbar Guidance

When this repository is executed through Busbar:

- Treat Busbar as the portfolio execution/control surface, not as repository authority. GitHub repository state remains authoritative.
- Claim coordinated work with `work.claim` before mutating an owned surface and settle the lease with `work.settle` when the outcome is final.
- Use existing Busbar semantic GitHub commands when their guarantees are needed: `github.apply_changeset`, `github.review_packet`, `github.delete_branch`, and `github.required_checks.ensure`. Use ordinary GitHub operations for ordinary GitHub behavior instead of recreating it in the control plane.
- Let `portfolio.reconcile_work_surface` derive the Linear work projection from GitHub. Do not use Linear as a second repository, evidence ledger, or historical archive.
- Keep reasoning agents on judgment, research, synthesis, design, debugging, and novel implementation. Move repeated bookkeeping, reconciliation, validation, counting, materialization, state derivation, and known recovery choreography into deterministic software.
- If an operation depends on Busbar guarantees such as exclusive claims, atomic changes, or protocol evidence and Busbar is unavailable, fail closed. Do not fall back to the historical Agent Execution Control Plane or add a compatibility path.
- Keep repository procedure executable and reviewable from versioned content and ordinary GitHub state even when Busbar performed the orchestration.

## Core invariants

- Prefer deletion, consolidation, and deterministic derivation over compatibility layers or competing mechanisms.
- Maintain one authoritative path for content storage, acquisition receipts, canonical identity, verification, normalization, release materialization, and generated projections.
- Move repeatable bookkeeping, reconciliation, counting, validation, materialization, and recovery into deterministic software rather than prompts or manual procedure.
- Source bytes and pinned upstream facts are immutable inputs.
- Every published row or artifact must remain traceable to provenance.
- Exact byte identity is the v1 deduplication boundary unless a separately specified semantic-equivalence layer says otherwise.
- Source-declared metrics are observations. Recompute authoritative metrics with the pinned verifier and preserve disagreements.
- Never hand-maintain generated counts, manifests, cards, indexes, or other derivable projections.
- Publication targets such as Hugging Face are downstream distributions, not authorities.
- Rights and redistribution policy are explicit. Never broaden publication rights by inference.

## Scope and concurrency

- Inspect open work and dependency edges before implementation.
- Work within one issue or packet unless the work graph explicitly permits parallel ownership.
- Do not modify another active item's owned surface without resolving the dependency or ownership conflict first.
- Branch from landed dependencies. Stack PRs only for real dependency edges or explicit collision avoidance.
- Keep scope narrow. If a task requires changing a neighboring public contract, split or restack the work instead of silently widening it.

## Fail closed

Reject ambiguous or unsafe state rather than guessing, especially for:

- mutated sources or corrupt cached objects;
- ambiguous puzzle/artifact mappings;
- unsupported or incompatible formats;
- provenance or identity conflicts;
- unsafe filesystem paths or staging overlap;
- rights-policy violations;
- incomplete required coverage when complete coverage is requested.

Do not hide these failures by dropping records, weakening policy, or adding hand-authored exceptions.

## Implementation discipline

- Prefer small typed interfaces with one clear owner.
- Keep acquisition, parsing, verification, normalization, materialization, and publication boundaries separate unless an established interface intentionally joins them.
- Source adapters translate upstream facts; they do not redefine canonical schemas or verification semantics.
- Preserve deterministic ordering and identity. Test order independence and local-root independence where relevant.
- Avoid repository-layout assumptions in installed-package behavior.
- Test public behavior when practical instead of importing private helpers solely for assertions.
- For behavior changes and bug fixes, add a focused failing regression before the fix, then run the relevant broader suite.
- Do not perform unrelated refactors while touching a subsystem.

## Validation

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

The ordinary pytest suite is hermetic. Tests marked `upstream` intentionally require pinned external revisions. If an upstream check cannot run, report that fact rather than treating it as passing.

Run focused checks while developing and fresh validation appropriate to the changed surface before merge. Changes affecting the release boundary should mirror the complete CI sequence above.

## Pull requests

PRs should state scope, dependencies, non-goals, stacking relationships, and fresh verification evidence.

Every PR merged to `main` must have a successful GitHub Actions `validate` check for the exact PR head being merged. A local run, mergeable state, or successful check on an older head is insufficient. Do not bypass the gate by direct push or administrative merge.

Completion means the landed state satisfies the issue acceptance criteria with fresh evidence, not merely that code exists or a branch is mergeable.

## Documentation

Update durable documentation when a contract, command, invariant, dependency, or architectural boundary changes. Do not duplicate fast-moving live status in repository prose.

Keep README focused on the usable repository shape, TODO on stable dependency/concurrency structure, and detailed contracts in focused documents. Prefer links to authoritative facts over copied prose. Names should describe the system that actually exists.
