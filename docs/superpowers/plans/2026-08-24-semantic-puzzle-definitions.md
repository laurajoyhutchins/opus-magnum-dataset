# First-Class Semantic Puzzle Definitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PuzzleDefinition` the canonical semantic problem representation while preserving exact `PuzzleArtifact` bytes as provenance and verifier inputs.

**Architecture:** Add one deterministic semantic evidence/reconciliation boundary, feed it from molecule-db and then a strict native format-3 `.puzzle` decoder, and finally migrate release, coverage, and research serialization consumers to semantic definitions. Verification remains paired to an explicitly selected exact artifact, and the release migration waits for WP-12 PR #58's owned surfaces.

**Tech Stack:** Python 3.12, JSON Schema draft 2020-12, dataclasses/typing, existing canonical JSON/SHA-256 helpers, pytest, Ruff, pinned omsim upstream contracts, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-24-semantic-puzzle-definitions-design.md`

## Global Constraints

- No second corpus, semantic sidecar store, compatibility layer, hand-maintained semantic index, second content store, or second release authority.
- Semantic identity excludes observations, artifact IDs/hashes/bytes, source ordering, and producer implementation version.
- Unknown source facts remain unknown; conflicts fail closed with puzzle/field/source context; there is no source-priority rule.
- WP-12 complete coverage continues to gate on verifier-ready exact artifacts, not semantic coverage.
- The native `.puzzle` decoder parses problem structure only; pinned `libverify`/omsim remains verification authority.
- Redistribution rights remain artifact-level facts and are never inferred from semantic availability.
- Every behavior change follows focused RED/GREEN tests before broader validation.

---

## PR A: Semantic contract and reconciliation

### Task 1: Centralize observation identity

**Files:** create `src/opus_corpus/observations.py`; modify `solution_materialization.py` and `release_materialization.py`; create `tests/test_observations.py`.

**Produces:** `observation_id(body: Mapping[str, Any]) -> str`, preserving the current `om.observation.sha256.<digest>` identities exactly.

- [ ] Write compatibility tests for representative existing observation bodies and field-order independence.
- [ ] Run `uv run pytest -q tests/test_observations.py` and verify RED because the shared helper is absent.
- [ ] Add the shared helper only, then migrate duplicate private helpers without changing bodies.
- [ ] Run focused + existing materialization tests; commit `refactor: centralize observation identity`.

### Task 2: Define PuzzleDefinition schema and identity

**Files:** create `src/opus_corpus/schemas/puzzle-definition.schema.json`, `src/opus_corpus/puzzle_definition.py`, `tests/test_puzzle_definition.py`; delete `normalized-puzzle.schema.json`; update packaged-schema tests.

**Produces:** immutable `PuzzleDefinitionEvidence`; canonical semantic record shape; `puzzle_definition_id(record)` derived from schema version, puzzle ID, and canonical semantic content only.

- [ ] Write RED tests proving complete definitions validate without artifacts; artifact/provenance/source order does not alter identity; molecule/bond order canonicalizes; repeated molecule multiplicity survives; invalid bond references fail.
- [ ] Run focused RED.
- [ ] Add strict schema and canonicalization/identity helpers using existing canonical JSON/SHA-256 utilities.
- [ ] Delete the obsolete artifact-bound normalized-puzzle schema and update package tests.
- [ ] Run focused + installed-schema tests; commit `feat: define canonical puzzle semantics`.

### Task 3: Reconcile semantic evidence

**Files:** modify `puzzle_definition.py`; extend `test_puzzle_definition.py`.

**Produces:** `reconcile_puzzle_definition(puzzle_id, evidence) -> PuzzleDefinitionResolution` and typed `PuzzleDefinitionConflictError`.

- [ ] Write RED tests for matching multi-source claims, order independence, partial merge, unresolved missing fields, scalar conflicts, and nested topology conflicts.
- [ ] Implement canonical field/path comparison with no source priority.
- [ ] Enforce cross-field invariants including `target_output_count == 6 * output_scale` and production/nullability.
- [ ] Run focused GREEN; commit `feat: reconcile puzzle semantic evidence`.

### Task 4: Feed molecule-db into shared evidence

**Files:** modify `adapters/molecule_db.py`, `puzzle_materialization.py`, `test_molecule_db.py`, `test_puzzle_materialization.py`.

- [ ] Write RED tests showing molecule-db claims topology/multiplicity only and does not invent availability, output scale, or production facts.
- [ ] Write reconciliation integration RED for corroboration and conflict.
- [ ] Translate existing molecule-db semantic parser output into `PuzzleDefinitionEvidence`.
- [ ] Replace boolean-style semantic coverage extraction with evidence routed to the reconciler, preserving exact-artifact materialization.
- [ ] Run focused tests + Ruff; commit `feat: feed molecule-db into puzzle semantics`.

### Task 5: Integrate PR A

**Files:** update `docs/dataset-spec.md`, `README.md`, and `docs/TODO.md` only where durable architecture/dependencies changed.

- [ ] Document `PuzzleDefinition` as the semantic authority and exact artifacts as provenance/verifier inputs.
- [ ] Run `uv run ruff check .`, `uv run pytest -q`, and `uv run opus-corpus collections validate`.
- [ ] Open/update PR A against `main` with #61 scope, non-goals, dependencies, and exact RED/GREEN evidence.

---

## PR B: Native `.puzzle` decoder and artifact evidence

### Task 6: Strict format-3 parser

**Files:** create `src/opus_corpus/puzzle_parser.py`, `tests/test_puzzle_parser.py`.

**Produces:** `parse_puzzle_bytes(payload: bytes) -> ParsedPuzzle`; bounded readers reject truncation instead of silently yielding zero.

- [ ] Write RED tests for valid minimal format-3 bytes, truncated integers/strings/molecules/production data, unsupported version, excessive counts, invalid bond endpoints, and trailing bytes.
- [ ] Implement strict little-endian and 7-bit string readers plus format-3 structures in pinned omsim parse order.
- [ ] Run focused GREEN + Ruff; commit `feat: parse opus magnum puzzle bytes`.

### Task 7: Decode artifact semantics

**Files:** create `puzzle_decoder.py`; modify `puzzle_materialization.py`; create `test_puzzle_decoder.py`; extend materialization tests.

**Produces:** `decode_puzzle_definition_evidence(parsed, *, puzzle_id, observation_id, puzzle_artifact_id)`; explicit availability/atom/bond vocabularies fail closed on unknown values/bits.

- [ ] Write RED vocabulary and output-target tests.
- [ ] Write RED integration proving byte-distinct artifacts with identical semantics reconcile to one definition, semantic disagreement conflicts, and verifier artifact selection remains separately strict.
- [ ] Implement decoding without simulation behavior and read artifacts only through authoritative `ContentStore` identity.
- [ ] Run focused GREEN; commit `feat: derive semantics from puzzle artifacts`.

### Task 8: Differential contract against pinned omsim

**Files:** create `tests/test_puzzle_parser_upstream.py`; change workflow only if existing upstream marker discovery requires it.

- [ ] Add `upstream` tests comparing availability, topology, output scale, and available production fields against exact pinned omsim fixtures/contract.
- [ ] Run `uv run pytest -q -o addopts= -m upstream`; retain exact evidence or state an explicit environment limitation.
- [ ] Run ordinary tests + Ruff; commit `test: cross-check puzzle decoder with omsim`.
- [ ] Open PR B stacked on PR A; retarget to `main` after PR A lands.

---

## PR C: Release, coverage, and research migration

### Task 9: Separate coverage axes

**Files:** modify `puzzle_materialization.py` and tests plus WP-12 coverage tests after #58 lands.

- [ ] RED tests for semantic-only, artifact-only, compatible multi-artifact, verifier-ambiguous, and verifier-ready states.
- [ ] Derive `puzzle_definition_id`, `semantic_covered`, `artifact_covered`, `verifier_ready`, exact IDs/sources, and semantic sources mechanically.
- [ ] Keep `require_complete_puzzle_coverage()` gating on `verifier_ready`.
- [ ] Run focused/WP-12 GREEN; commit `feat: separate puzzle coverage axes`.

### Task 10: Migrate release puzzle rows

**Files:** modify `schemas/puzzle.schema.json`, `release_materialization.py`, any puzzle-specific release payload policy, tiny puzzle fixture, release tests, and WP-12 tests.

- [ ] RED tests proving release puzzle rows need a complete semantic definition but no binary payload fields.
- [ ] Replace `canonical_puzzle_artifact_id`, `puzzle_sha256`, `puzzle_bytes`, and artifact `rights_status` with the semantic definition/provenance surface.
- [ ] Make release materialization validate `PuzzleDefinition` identity without reading puzzle bytes for the puzzle row.
- [ ] Preserve exact `puzzle_artifact_id` in verification lineage.
- [ ] Run release/WP-12 GREEN; commit `feat: publish semantic puzzle definitions`.

### Task 11: Migrate model/research serialization

**Files:** modify `serialization.py`, `test_serialization.py`, `dataset-spec.md`, `hugging-face-export.md`, `README.md`; remove obsolete production `normalized-puzzle` terminology.

- [ ] RED serializer tests for semantic definitions without binary fields.
- [ ] Make puzzle serialization explicitly consume `PuzzleDefinition`; keep solution serialization normalized-solution specific.
- [ ] Delete obsolete artifact-bound puzzle-normalization aliases/references.
- [ ] Update research/export docs; run focused GREEN; commit `refactor: make puzzle serialization semantic`.

### Task 12: Full release-boundary verification

- [ ] `uv sync --all-extras --locked`
- [ ] `uv run ruff check .`
- [ ] `uv run pytest -q`
- [ ] `uv run pytest -q -o addopts= -m upstream`
- [ ] `uv run opus-corpus collections validate`
- [ ] Tiny release build/validate/stage sequence from `AGENTS.md`
- [ ] WP-12 v1 runner regressions from #58
- [ ] Open PR C only after PR B and #58 land, or explicitly base on a temporary branch containing both dependencies.
- [ ] Require successful GitHub Actions `validate` on exact PR-C head before merge.

## Completion

Close #61 only when all three capabilities land with fresh evidence for artifact-independent semantic materialization, deterministic conflict-safe reconciliation, strict native decoding and pinned upstream agreement, independent coverage axes, semantic release/research consumers, and unchanged exact-artifact verifier authority.
