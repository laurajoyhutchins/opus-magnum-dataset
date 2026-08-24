# Canonical Verification Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class canonical Verification schema, deterministic identity helper, and simulator-independent verifier protocol.

**Architecture:** Verification is derived from exact puzzle/solution artifacts plus pinned verifier/profile identity. The PR adds only a strict domain contract and tests; acquisition, simulator integration, parsing, normalization, and release projection remain separate.

**Tech Stack:** Python 3.12, dataclasses, typing.Protocol, jsonschema 4.26.0, pytest 9.0.2, existing canonical hashing helpers.

**Spec:** `docs/superpowers/specs/2026-08-24-verification-contract-design.md`

## Global Constraints

- Start from current `main`, which contains #6 and #9.
- Do not depend on `feature/artifact-ingestion`.
- Verification IDs depend only on artifact pair, verifier identity, and validation profile, never result values.
- Do not modify acquisition/cache code or integrate `omsim`/`libverify`.
- Do not remove flattened verification fields from the existing solution release schema in this PR.
- Reuse `canonical_json_bytes()` and `sha256_bytes()` from `src/opus_corpus/hashing.py`.

---

### Task 1: Verification contract tests

**Files:**
- Create: `tests/test_verification.py`

**Interfaces:**
- Consumes: `jsonschema.Draft202012Validator`; future `VerificationInput`, `VerificationResult`, `Verifier`, `verification_id`.
- Produces: executable contract for schema validation, identity behavior, and protocol usability.

- [ ] Write failing schema and identity tests.
- [ ] Run CI and verify RED for the missing verification module/schema.
- [ ] Commit with `test: define verification contract`.

### Task 2: Verification schema

**Files:**
- Create: `schemas/verification.schema.json`

- [ ] Add the minimal strict schema from the spec.
- [ ] Run focused/full CI; schema tests should pass while Python-module tests remain the only feature gap until Task 3 lands.
- [ ] Commit with `feat: add canonical verification schema`.

### Task 3: Simulator-independent verification types and identity

**Files:**
- Create: `src/opus_corpus/verification.py`

**Produces:**
- `VerificationInput`
- `VerificationResult`
- `Verifier`
- `verification_id(*, puzzle_artifact_id, solution_id, verifier_implementation, verifier_revision, verifier_sha256, validation_profile) -> str`

- [ ] Add frozen dataclasses and the protocol.
- [ ] Implement deterministic ID generation with `canonical_json_bytes()` and `sha256_bytes()`.
- [ ] Run CI and verify GREEN.
- [ ] Require Ruff, full pytest, frozen collection validation, and tiny release build/validate/stage to pass.
- [ ] Commit with `feat: stub canonical verification contract`.

## Self-review

The plan covers the schema, deterministic identity, protocol/data classes, successful/failed records, compatibility boundary, and explicit non-goals. Types and identity fields match the design spec.
