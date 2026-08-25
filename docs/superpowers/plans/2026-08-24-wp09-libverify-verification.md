# WP-09 libverify Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce deterministic canonical `Verification` records from canonical puzzle/solution artifacts using pinned `omsim` `libverify`.

**Architecture:** Keep the existing `Verifier` contract authoritative. Add a native libverify adapter that consumes exact bytes and a separate deterministic materializer that pairs landed WP-04/WP-08 artifacts, reads bytes through `ContentStore`, and invokes any `Verifier` implementation.

**Tech Stack:** Python 3.12, stdlib `ctypes`, existing `ContentStore`/artifact contracts, pytest, pinned upstream C `libverify` built with `cc` in the marked upstream test.

**Spec:** `docs/superpowers/specs/2026-08-24-wp09-libverify-verification-design.md`

## Global Constraints

- Pin `omsim` revision `758f4a4b4c9e24f50294801da774a0960c922bab`.
- Treat the native shared library as a separately pinned runtime input and verify its expected SHA-256 before loading it.
- Use validation profile `omsim-libverify-v1` with an explicit 150000-cycle limit.
- Recompute `cost`, `instructions`, `cycles`, and `area`; never trust source claims as verification facts.
- Do not equate simulator success with ordinary constructibility or record eligibility.
- Do not create new acquisition, storage, normalized-data, or release authorities.
- Preserve deterministic logical output across repeated runs, artifact input ordering, and cache-root location.

---

### Task 1: Define the libverify behavior contract with failing tests

**Files:**
- Create: `tests/test_libverify.py`
- Create: `src/opus_corpus/libverify.py`

**Interfaces:**
- Consumes: `VerificationInput`, `VerificationResult`, `verification_id`, `sha256_file`.
- Produces: `OMSIM_LIBVERIFY_REVISION`, `OMSIM_LIBVERIFY_PROFILE`, `LibverifyBackend`, `LibverifyVerifier`.

- [ ] **Step 1: Write tests before production behavior**

Cover a scripted backend for: successful metric recomputation, unsupported profile rejection, puzzle parse failure, solution parse failure, parse/decode failure discovered during metric evaluation, simulation failure, metric failure, stable error details, handle destruction, repeated-result determinism, and `vanilla_constructible`/`record_eligible` remaining `None` on simulator success.

The successful case must assert exact verifier identity, binary hash passthrough, profile identity, four metrics, and deterministic `verification_id`.

- [ ] **Step 2: Run the focused test in CI and verify RED**

Run: `uv run pytest -q tests/test_libverify.py`

Expected: collection/import failure because `opus_corpus.libverify` does not yet exist.

- [ ] **Step 3: Implement the minimal mapping layer**

Create constants and a `LibverifyBackend` protocol with operations to create/destroy a verifier handle, set the cycle limit, read the current error/source/cycle/location, and evaluate integer metrics.

`LibverifyVerifier.verify()` must reject profiles other than `omsim-libverify-v1`, create from exact bytes, map puzzle/solution parse errors as `parse_status=failed` even when discovered during metric evaluation, set the cycle limit to 150000, evaluate `cost`, `instructions`, `cycles`, `area`, and always destroy the handle in `finally`.

- [ ] **Step 4: Run focused and existing verification tests**

Run: `uv run pytest -q tests/test_libverify.py tests/test_verification.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: implement libverify verifier mapping`

---

### Task 2: Implement and exercise the ctypes native backend

**Files:**
- Modify: `src/opus_corpus/libverify.py`
- Modify: `tests/test_libverify.py`

**Interfaces:**
- Consumes: a local shared-library `Path` plus an independently pinned expected SHA-256.
- Produces: `CtypesLibverifyBackend.from_path(path, expected_sha256=...)` and `LibverifyVerifier.from_library(path, expected_sha256=...)`.

- [ ] **Step 1: Add failing tests for native-boundary configuration**

Use a fake `ctypes.CDLL` object to assert that the backend hashes the exact library file, refuses a hash mismatch before loading, configures the documented libverify signatures only for matching bytes, passes byte arrays with explicit lengths to `verifier_create_from_bytes`, decodes nullable C strings as UTF-8, and exposes integer error/metric values.

- [ ] **Step 2: Verify RED in CI**

Run: `uv run pytest -q tests/test_libverify.py`

Expected: FAIL because the ctypes backend/factory does not exist.

- [ ] **Step 3: Implement the ctypes wrapper**

Hash the supplied native file first and compare it to `expected_sha256`; fail closed before `ctypes.CDLL` if the digest differs. Bind exactly these symbols from upstream `verifier.h`: `verifier_create_from_bytes`, `verifier_destroy`, `verifier_set_cycle_limit`, `verifier_error`, `verifier_error_source`, `verifier_error_cycle`, `verifier_error_location_u`, `verifier_error_location_v`, and `verifier_evaluate_metric`.

Use `ctypes.create_string_buffer` for puzzle and solution bytes so embedded NULs are preserved through explicit lengths. Do not expose ctypes types above the backend boundary.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest -q tests/test_libverify.py tests/test_verification.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: bind pinned libverify through ctypes`

---

### Task 3: Materialize verification records from canonical artifacts

**Files:**
- Create: `src/opus_corpus/verification_materialization.py`
- Create: `tests/test_verification_materialization.py`

**Interfaces:**
- Consumes: `Iterable[ArtifactRecord]` for puzzle/solution artifacts, existing `ContentStore`, a `Verifier`, and validation-profile string.
- Produces: `materialize_verifications(...) -> tuple[VerificationResult, ...]` and `VerificationMaterializationError`.

- [ ] **Step 1: Write failing public-behavior tests**

Cover one puzzle/solution success path, multiple solutions for one puzzle, missing puzzle artifact, multiple puzzle artifacts for one puzzle, wrong artifact kinds, corrupt/missing content objects, schema-invalid verifier output, deterministic output across reversed input order, and exact byte delivery to the verifier.

- [ ] **Step 2: Verify RED in CI**

Run: `uv run pytest -q tests/test_verification_materialization.py`

Expected: collection/import failure because the module does not yet exist.

- [ ] **Step 3: Implement deterministic materialization**

Index puzzle artifacts by `puzzle_id` and fail unless each referenced solution puzzle resolves to exactly one puzzle artifact. Validate artifact kinds and `.puzzle`/`.solution` formats. Read both objects with `ContentStore.require()` and pass their exact bytes to `VerificationInput`. Validate each returned `VerificationResult` against the package-native canonical verification schema before accepting its lineage/profile/identity. Sort solution artifacts by stable artifact identity before evaluation and return results sorted by `verification_id`.

- [ ] **Step 4: Verify GREEN and regression surface**

Run: `uv run pytest -q tests/test_verification_materialization.py tests/test_puzzle_materialization.py tests/test_solution_materialization.py tests/test_verification.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: materialize canonical verification records`

---

### Task 4: Prove the pinned native integration and document the landed contract

**Files:**
- Create: `tests/test_libverify_upstream.py`
- Create: `docs/verification.md`
- Modify: `README.md`
- Modify: `docs/TODO.md`

**Interfaces:**
- Consumes: pinned `omsim` tarball and the production ctypes adapter.
- Produces: a real upstream contract proving the pinned C ABI and metric names used by WP-09.

- [ ] **Step 1: Add the upstream contract before final documentation state**

Mark the test `@pytest.mark.upstream`. Download the exact pinned omsim tarball with existing GitHub-source helpers, extract only the six C sources and six headers required by the upstream Makefile plus a known matching test puzzle/solution pair, compile a temporary `libverify.so` with `cc -O2 -std=c11 -pedantic -Wall -Wno-missing-braces -g -shared -fpic ... -lm`, hash the resulting binary, pass that digest as `expected_sha256` to `LibverifyVerifier.from_library()`, and verify the real bytes. Assert parse/simulation success, non-negative recomputed metrics, pinned revision/profile, binary SHA-256, and identical repeated results.

This contract proves FFI compatibility and binary-pin enforcement for that build invocation. It does not claim universal cross-toolchain binary reproducibility.

- [ ] **Step 2: Run the upstream contract and full workflow**

Run:

```bash
uv run ruff check .
uv run pytest -q
uv run pytest -q -o addopts= -m upstream
uv run opus-corpus collections validate
uv run opus-corpus release build base-game-2026-06-16 --input fixtures/tiny-corpus --output .tmp-release --payload-policy metadata-only --coverage-policy subset
uv run opus-corpus release validate base-game-2026-06-16 --output .tmp-release
uv run opus-corpus release stage base-game-2026-06-16 --output .tmp-release --destination .tmp-stage
```

Expected: all commands PASS.

- [ ] **Step 3: Update durable documentation**

Document verifier source pin, separately pinned runtime binary digest, profile/cycle-limit semantics, parse/decode versus simulation failure mapping, canonical result schema validation, simulator-valid versus constructibility/record predicates, and the artifact materialization boundary. Mark WP-09 settled in `docs/TODO.md` only after the full validation workflow is green.

- [ ] **Step 4: Commit**

Commit message: `docs: document deterministic libverify verification`
