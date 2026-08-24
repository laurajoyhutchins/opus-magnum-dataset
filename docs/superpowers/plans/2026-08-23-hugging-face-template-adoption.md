# Hugging Face Template Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Opus Magnum dataset repository into a self-contained, deterministic four-config Hugging Face release factory by adopting and specializing the existing Hugging Face dataset template machinery.

**Architecture:** One `opus_corpus` Python package owns collection validation, canonical release validation, deterministic Parquet materialization, release manifests, generated dataset cards, staging, and publication guards. Canonical Opus facts remain checked-in collection/source facts or explicit build inputs; generated Parquet, manifests, and Hub cards remain downstream projections. The generic release layer never interprets simulator semantics and enforces rights policy only from explicit canonical row fields.

**Tech Stack:** Python 3.12, `jsonschema` Draft 2020-12, PyArrow/Parquet with Zstandard, `huggingface_hub`, pytest, Ruff, uv lockfile.

**Spec:** `docs/superpowers/specs/2026-08-23-hugging-face-template-adoption-design.md`

## Global Constraints

- Minimum Python version: 3.12.
- Required Hugging Face configs: `puzzles`, `solutions`, `observations`, `normalized`.
- General corpus split names are immutable collection IDs with `-` replaced by `_`; never use `train`, `validation`, or `test`.
- Collection authority remains `collections/*.toml` plus the referenced CSV inventory; no generated catalog or validation ledger is committed.
- Payload policies are exactly `metadata-only` and `include-permitted`.
- `include-permitted` may expose raw bytes only when `rights_status == "redistributable"`; `metadata-only` exposes no raw puzzle or solution bytes.
- Logical row reproducibility is the normative v1 contract; physical Parquet hashes are recorded but byte-identical Parquet is not claimed.
- Generated Hub staging contains only `README.md`, `release-manifest.json`, and `data/**/*.parquet`.
- Tests require no network access.

---

### Task 1: Unified package and collection validator

**Files:**
- Create: `pyproject.toml`
- Create: `src/opus_corpus/__init__.py`
- Create: `src/opus_corpus/__main__.py`
- Create: `src/opus_corpus/errors.py`
- Create: `src/opus_corpus/hashing.py`
- Create: `src/opus_corpus/collections.py`
- Create: `schemas/collection-manifest.schema.json`
- Create: `schemas/collection-inventory-row.schema.json`
- Create: `tests/test_collections.py`

**Interfaces:**
- Produces `ValidationError(code: str, detail: str, path: str | None = None, row: int | None = None)` and `CollectionValidationError`.
- Produces `sha256_file(path: Path) -> str` and `canonical_records_sha256(records: Sequence[Mapping[str, Any]]) -> str`.
- Produces `validate_collection(manifest_path: Path) -> CollectionDefinition` and `validate_all_collections(root: Path) -> list[CollectionDefinition]`.
- `CollectionDefinition` exposes `collection_id`, `inventory_sha256`, `puzzle_count`, `manifest_path`, and parsed inventory rows.

- [ ] **Step 1: Write failing collection tests**

Create tests that assert the committed `base-game-2026-06-16.toml` validates and that synthetic fixtures reject hash drift, duplicate canonical IDs, duplicate game IDs, duplicate leaderboard keys, non-contiguous IDs, malformed row values, wrong CSV headers, count mismatch, unmatched/overlapping group rollups, path traversal, and malformed TOML. Assert error codes rather than matching prose.

```python
def test_committed_collection_validates(repo_root: Path):
    result = validate_collection(repo_root / "collections/base-game-2026-06-16.toml")
    assert result.collection_id == "base-game-2026-06-16"
    assert result.puzzle_count == 166


def test_inventory_hash_drift_is_rejected(collection_fixture):
    collection_fixture.inventory.write_text(collection_fixture.inventory.read_text() + "\n")
    with pytest.raises(CollectionValidationError) as exc:
        validate_collection(collection_fixture.manifest)
    assert "inventory_hash_mismatch" in {e.code for e in exc.value.errors}
```

- [ ] **Step 2: Run collection tests and verify RED**

Run: `uv run pytest tests/test_collections.py -q`
Expected: import/feature failures because `opus_corpus.collections` does not exist.

- [ ] **Step 3: Implement the minimal unified validator**

Use `tomllib`, `csv`, `jsonschema.Draft202012Validator`, and SHA-256 helpers. Require the exact ordered inventory header, resolve inventories only within the manifest directory, validate each row against the row schema, accumulate deterministic errors, enforce uniqueness/sequence/count/group-rollup rules, and return immutable parsed collection data without writing generated state.

- [ ] **Step 4: Run collection tests and verify GREEN**

Run: `uv run pytest tests/test_collections.py -q`
Expected: all collection tests pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/opus_corpus schemas/collection-*.json tests/test_collections.py
git commit -m "feat: unify collection validation toolchain"
```

---

### Task 2: Canonical four-config inputs, sorting, schemas, and payload policy

**Files:**
- Create: `schemas/puzzle.schema.json`
- Create: `schemas/solution.schema.json`
- Create: `schemas/observation.schema.json`
- Create: `schemas/normalized.schema.json`
- Create: `src/opus_corpus/config.py`
- Create: `src/opus_corpus/release_inputs.py`
- Create: `src/opus_corpus/payload.py`
- Create: `tests/test_release_inputs.py`
- Create: `fixtures/tiny-corpus/puzzles.jsonl`
- Create: `fixtures/tiny-corpus/solutions.jsonl`
- Create: `fixtures/tiny-corpus/observations.jsonl`
- Create: `fixtures/tiny-corpus/normalized.jsonl`
- Create: `fixtures/tiny-corpus/release-metadata.json`

**Interfaces:**
- Produces `CorpusConfig` loaded by `load_config(path: Path) -> CorpusConfig`.
- Produces `load_release_inputs(input_dir: Path, schemas_dir: Path) -> dict[str, list[dict[str, Any]]]`.
- Produces `sort_records(config_name: str, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]`.
- Produces `validate_payload_policy(config_name: str, rows: Sequence[dict[str, Any]], policy: str) -> None`.

- [ ] **Step 1: Write failing schema/sorting/payload tests**

Cover invalid rows for every config, stable ordering regardless of JSONL file order, metadata-only rejection of non-null `puzzle_bytes`/`solution_bytes`, and include-permitted acceptance only for `rights_status == "redistributable"`.

```python
def test_solution_sort_is_canonical():
    rows = [
        {"puzzle_id": "om.puzzle.0002", "solution_id": "s2"},
        {"puzzle_id": "om.puzzle.0001", "solution_id": "s9"},
    ]
    assert [(r["puzzle_id"], r["solution_id"]) for r in sort_records("solutions", rows)] == [
        ("om.puzzle.0001", "s9"),
        ("om.puzzle.0002", "s2"),
    ]


def test_metadata_only_rejects_solution_bytes():
    with pytest.raises(PayloadPolicyError):
        validate_payload_policy("solutions", [{"rights_status": "redistributable", "solution_bytes": "AA=="}], "metadata-only")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_release_inputs.py -q`
Expected: missing modules/interfaces.

- [ ] **Step 3: Implement minimal loaders, schemas, sorting, and rights checks**

Read exact `<config>.jsonl` fixture files, validate every row with Draft 2020-12, preserve source file hashes for the release manifest, and sort by the export-contract keys. Store fixture bytes as base64 strings at the JSON boundary and convert them to binary immediately before Arrow materialization.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_release_inputs.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add schemas/*.schema.json src/opus_corpus/config.py src/opus_corpus/release_inputs.py src/opus_corpus/payload.py tests/test_release_inputs.py fixtures/tiny-corpus
git commit -m "feat: validate canonical release inputs"
```

---

### Task 3: Deterministic Parquet build and release manifest validation

**Files:**
- Create: `src/opus_corpus/parquet.py`
- Create: `src/opus_corpus/release.py`
- Create: `tests/test_parquet.py`
- Create: `tests/test_release.py`

**Interfaces:**
- Produces `build_release(collection: CollectionDefinition, input_dir: Path, output_dir: Path, config: CorpusConfig, payload_policy: str) -> ReleaseManifest`.
- Produces `validate_release(collection: CollectionDefinition, output_dir: Path, config: CorpusConfig) -> ReleaseManifest`.
- Produces `write_parquet(config_name: str, rows: Sequence[dict[str, Any]], path: Path, config: CorpusConfig) -> None`.
- `ReleaseManifest` serializes deterministically to `release-manifest.json` and includes per-config schema hash, logical-record hash, row count, Parquet path/hash, source hashes, collection inventory hash, build config hash, payload policy, release metadata, and `logical_release_sha256`.

- [ ] **Step 1: Write failing Parquet/manifest tests**

Test all four configs are written under `data/<config>/<split>-00000-of-00001.parquet`, Parquet rows round-trip to schema-valid canonical content, repeated builds have identical logical hashes, source/schema/output drift is detected, and the overall release hash excludes its own hash field before hashing.

```python
def test_tiny_release_builds_four_configs(tiny_release):
    manifest = tiny_release.manifest
    assert set(manifest.configs) == {"puzzles", "solutions", "observations", "normalized"}
    assert manifest.collection_id == "base-game-2026-06-16"


def test_repeated_builds_have_same_logical_release_hash(build_twice):
    first, second = build_twice
    assert first.logical_release_sha256 == second.logical_release_sha256
    assert {k: v.records_sha256 for k, v in first.configs.items()} == {
        k: v.records_sha256 for k, v in second.configs.items()
    }
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_parquet.py tests/test_release.py -q`
Expected: missing build/release interfaces.

- [ ] **Step 3: Implement minimal builder and validator**

Use explicit PyArrow writer settings from config, deterministic row order, stable JSON serialization for logical hashes, per-config schema/source/output hashes, and atomic manifest writing after all four Parquet files succeed. Validation rereads Parquet, reapplies schemas and payload policy, recomputes logical hashes/counts/output hashes, and rejects drift.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_parquet.py tests/test_release.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/opus_corpus/parquet.py src/opus_corpus/release.py tests/test_parquet.py tests/test_release.py
git commit -m "feat: build deterministic corpus releases"
```

---

### Task 4: Generated dataset card, Hub staging, and publication guards

**Files:**
- Create: `src/opus_corpus/card.py`
- Create: `src/opus_corpus/publish.py`
- Create: `tests/test_card.py`
- Create: `tests/test_publish.py`

**Interfaces:**
- Produces `render_dataset_card(manifest: ReleaseManifest, metadata: Mapping[str, Any]) -> str`.
- Produces `stage_release(collection: CollectionDefinition, output_dir: Path, destination: Path, config: CorpusConfig) -> Path`.
- Produces `publish_release(collection: CollectionDefinition, output_dir: Path, config: CorpusConfig, token: str | None = None) -> str`.

- [ ] **Step 1: Write failing card/staging tests**

Assert YAML front matter maps all four config names to the immutable split and exact Parquet paths, release facts are derived from manifest/metadata, staging contains only the projection allowlist, placeholder/malformed Hub IDs are refused, and no fixture/schema/source files are staged.

```python
def test_card_has_four_hf_configs(release_manifest, release_metadata):
    card = render_dataset_card(release_manifest, release_metadata)
    assert "config_name: puzzles" in card
    assert "config_name: solutions" in card
    assert "split: base_game_2026_06_16" in card


def test_stage_is_projection_only(staged_release):
    files = {p.relative_to(staged_release).as_posix() for p in staged_release.rglob("*") if p.is_file()}
    assert files == {
        "README.md",
        "release-manifest.json",
        "data/puzzles/base_game_2026_06_16-00000-of-00001.parquet",
        "data/solutions/base_game_2026_06_16-00000-of-00001.parquet",
        "data/observations/base_game_2026_06_16-00000-of-00001.parquet",
        "data/normalized/base_game_2026_06_16-00000-of-00001.parquet",
    }
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_card.py tests/test_publish.py -q`
Expected: missing card/publish interfaces.

- [ ] **Step 3: Implement generation, staging, and guarded publish**

Generate the card from release metadata rather than copying the repository README. Stage only validated generated artifacts. Publish through `huggingface_hub.HfApi` after validation, reject placeholder/malformed IDs before importing network behavior, and use exact-projection upload semantics so stale Hub files are deleted.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_card.py tests/test_publish.py -q`
Expected: all tests pass without network access.

- [ ] **Step 5: Commit**

```bash
git add src/opus_corpus/card.py src/opus_corpus/publish.py tests/test_card.py tests/test_publish.py
git commit -m "feat: generate and stage Hugging Face projection"
```

---

### Task 5: CLI, locked environment, CI, and end-to-end tiny slice

**Files:**
- Create: `src/opus_corpus/cli.py`
- Create: `corpus.toml`
- Create: `.github/workflows/validate.yml`
- Create: `.github/workflows/publish.yml`
- Create: `tests/test_cli.py`
- Create: `uv.lock`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-23-collection-validator-design.md`

**Interfaces:**
- `opus-corpus collections validate [manifest]`
- `opus-corpus release build <collection> --input <path> --output <path> --payload-policy <policy>`
- `opus-corpus release validate <collection> --output <path>`
- `opus-corpus release stage <collection> --output <path> --destination <path>`
- `opus-corpus release publish <collection> --output <path>`

- [ ] **Step 1: Write failing CLI/end-to-end tests**

Exercise CLI exit codes and one full offline sequence against the committed tiny fixture: collection validation, metadata-only build, release validation, stage, and exact staged file list.

```python
def test_tiny_fixture_end_to_end(cli_runner, tmp_path):
    out = tmp_path / "release"
    assert cli_runner("collections", "validate").returncode == 0
    assert cli_runner("release", "build", "base-game-2026-06-16", "--input", "fixtures/tiny-corpus", "--output", str(out), "--payload-policy", "metadata-only").returncode == 0
    assert cli_runner("release", "validate", "base-game-2026-06-16", "--output", str(out)).returncode == 0
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_cli.py -q`
Expected: CLI command surface is missing.

- [ ] **Step 3: Implement CLI/config and CI wiring**

Use `argparse` with stable exit classes: `0` success, `1` validation/data failure, `2` configuration/operational misuse. Add `corpus.toml` with explicit writer settings and Hub placeholder ID. `validate.yml` installs from the lockfile, runs Ruff, the full pytest suite, collection validation, tiny build, and tiny release validation. `publish.yml` is manual-only and requires `HF_TOKEN` before invoking `release publish`.

- [ ] **Step 4: Generate and commit the lockfile**

Run: `uv lock`
Expected: `uv.lock` pins the exact resolved environment used by CI.

- [ ] **Step 5: Run the full verification suite**

Run:

```bash
uv sync --all-extras --locked
uv run ruff check .
uv run pytest -q
uv run opus-corpus collections validate
rm -rf .tmp-release .tmp-stage
uv run opus-corpus release build base-game-2026-06-16 --input fixtures/tiny-corpus --output .tmp-release --payload-policy metadata-only
uv run opus-corpus release validate base-game-2026-06-16 --output .tmp-release
uv run opus-corpus release stage base-game-2026-06-16 --output .tmp-release --destination .tmp-stage
```

Expected: every command exits `0`; `.tmp-stage` contains only the four Parquet files, `release-manifest.json`, and generated `README.md`.

- [ ] **Step 6: Update project docs and mark the old toolchain decision superseded**

README must describe the implemented release shell as available while keeping full acquisition/verification explicitly future work. The earlier collection-validator design must retain its semantic rules but state that its standalone stdlib-only toolchain decision is superseded by the unified `opus_corpus` package.

- [ ] **Step 7: Commit**

```bash
git add src/opus_corpus/cli.py corpus.toml .github/workflows tests/test_cli.py uv.lock README.md docs/superpowers/specs/2026-08-23-collection-validator-design.md
git commit -m "feat: complete tiny corpus release factory"
```

---

## Plan self-review

- Spec coverage: collection validation, four canonical configs, rights policy, deterministic logical hashing, Parquet materialization, manifest generation/validation, generated card, projection-only staging, publication guards, CLI, tiny fixture, CI, and locked dependencies are each assigned to an explicit task.
- Scope: full source acquisition, `omsim`, normalization implementation, Pareto derivation, complete source coverage, and byte-identical Parquet promises remain intentionally excluded.
- Type consistency: later tasks consume the `CollectionDefinition`, `CorpusConfig`, `ReleaseManifest`, sorting/payload helpers, and release functions defined by earlier tasks under the same names.
- Authority check: no task introduces a second collection catalog, generated ledger, or runtime dependency on the template repository.
