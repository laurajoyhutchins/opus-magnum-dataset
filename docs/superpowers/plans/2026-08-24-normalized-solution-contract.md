# Normalized Solution Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the normalized-solution structural schema and add a deterministic, parser-independent solution normalizer seam.

**Architecture:** Normalization is derived state over exact solution bytes. `normalized_solution_id` depends only on `solution_id`, `puzzle_id`, and `normalizer_version`; the normalizer protocol consumes bytes and returns a mapping that the existing serializer seam can project.

**Tech Stack:** Python 3.12, dataclasses, typing.Protocol, jsonschema, pytest, existing canonical hashing helpers.

**Spec:** `docs/superpowers/specs/2026-08-24-normalized-solution-contract-design.md`

## Global Constraints

- Base on PR #13's verified head.
- Do not implement `.solution` parsing, verification, acquisition, or release orchestration.
- Harden `schemas/normalized.schema.json` in place; do not add a parallel release config.
- Keep the existing `NormalizedSerializer` seam unchanged.
- Reuse `canonical_json_bytes()` and `sha256_bytes()`.

### Task 1: Structural and identity contract tests

**Files:**
- Create: `tests/test_normalization.py`

- [ ] Add a representative valid normalized record.
- [ ] Add rejection tests for unknown part fields, invalid rotation, negative cycles, and unknown summary fields.
- [ ] Add deterministic/change-sensitive normalized ID tests.
- [ ] Add protocol seam and fake normalizer tests.
- [ ] Run CI and verify RED against the existing permissive schema and missing `opus_corpus.normalization` module.
- [ ] Commit with `test: define normalized solution contract`.

### Task 2: Harden schema and migrate tiny fixture

**Files:**
- Modify: `schemas/normalized.schema.json`
- Modify: `fixtures/tiny-corpus/normalized.jsonl`

- [ ] Replace arbitrary nested objects with the strict structural shapes in the design spec.
- [ ] Keep `part.parameters` as the explicit extensible type-specific object.
- [ ] Update the tiny normalized fixture to the hardened shape and deterministic summary fields.
- [ ] Run CI and verify schema tests/fixture validation pass while normalization-module tests remain RED.
- [ ] Commit with `feat: harden normalized solution schema`.

### Task 3: Parser-independent normalization seam

**Files:**
- Create: `src/opus_corpus/normalization.py`

- [ ] Add `NormalizedSolutionRecord`, frozen/slotted `SolutionNormalizationInput`, and runtime-checkable `SolutionNormalizer` protocol.
- [ ] Add deterministic `normalized_solution_id(...)` using canonical JSON and SHA-256.
- [ ] Run CI and require full GREEN: Ruff, full pytest, frozen collection validation, tiny release build/validate/stage.
- [ ] Commit with `feat: stub solution normalization contract`.

## Review

Compare this branch against PR #13's frozen head. Reject any adapter/cache/simulator changes and any duplicate serializer or materialization path. Strengthen missing contract assertions before marking the PR ready.
