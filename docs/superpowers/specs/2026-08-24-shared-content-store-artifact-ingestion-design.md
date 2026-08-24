# Shared Content Store and Artifact Ingestion Design

## Goal

Create one authoritative exact-byte storage primitive and build deterministic artifact/provenance ingestion on top of the acquisition receipts already produced on `main`.

The change must preserve the current acquisition cache layout and receipt semantics while preventing downstream ingestion from creating a second byte store, reopening arbitrary source files, or inventing verifier/release facts.

## Context

Current `main` already has a `ContentAddressedCache` used by the landed `om-archive` and `om-leaderboard` acquisition adapters.

`ContentAddressedCache` currently owns two responsibilities:

1. storing exact payload bytes under a SHA-256-addressed object path;
2. storing source-specific immutable `CacheReceipt` records keyed by source ID, pinned revision, and upstream path.

The current object layout is:

`objects/sha256/<first-two-hex>/<remaining-62-hex>`

The current receipt contains:

- `source_id`;
- `revision`;
- `upstream_path`;
- `sha256`;
- `byte_length`;
- `rights_status`;
- `retrieved_at`.

Acquisition adapters already preserve exact source payloads and stable receipt evidence. Therefore downstream artifact ingestion should consume that evidence rather than read and republish source files itself.

A historical artifact-ingestion branch demonstrated useful logical contracts and invariants, but it independently implemented another SHA-256 publisher. That storage implementation is intentionally not carried forward.

## Decision

Split exact-byte object storage from source-receipt management, then add receipt-based artifact ingestion.

Add a focused `src/opus_corpus/content_store.py` containing the single authoritative content-addressed byte-store primitive.

Refactor `src/opus_corpus/cache.py` so `ContentAddressedCache` delegates object storage and integrity checks to `ContentStore` while retaining ownership of source receipt identity and persistence.

Add `src/opus_corpus/ingestion.py` for deterministic artifact/provenance materialization from acquisition receipts plus canonical puzzle association supplied by orchestration.

The dependency direction is:

`source adapter -> ContentAddressedCache -> ContentStore`

and later:

`receipt-aware orchestration -> ingestion -> ContentStore`

`ingestion` must not depend on concrete adapters. `ContentStore` must not depend on acquisition receipts or artifact semantics.

## Content store contract

### `StoredObject`

`StoredObject` is a frozen value type with:

- `sha256`: lowercase 64-hex digest;
- `byte_length`: exact byte length;
- `object_key`: cache-root-relative POSIX path using the existing layout, for example `objects/sha256/ba/7816...`.

`object_key` is stable metadata. Absolute local paths are never canonical values.

### `ContentStore`

`ContentStore(root: Path)` owns exact object bytes under `root`.

Public operations:

- `put_bytes(payload: bytes) -> StoredObject`
- `require(sha256: str, byte_length: int) -> StoredObject`
- `object_path(sha256: str) -> Path`

`put_bytes` computes SHA-256 over exact bytes using the repository hashing primitive and publishes them at the existing object path. If an object already exists, it verifies that the target is a regular file, hashes to the requested digest, and has the expected byte length. It never silently overwrites a mismatching existing object.

`require` validates the digest syntax, locates the existing object, requires a regular file, recomputes SHA-256 using the repository file-hashing primitive, and checks byte length. Missing or corrupt objects fail closed with a typed content-store error.

The content store does not know source IDs, revisions, upstream paths, retrieval timestamps, rights, puzzle IDs, artifact kinds, verifier state, or release schemas.

### Publication safety

First-write publication uses a temporary file under the target filesystem followed by a non-overwriting publication step. A concurrent writer that publishes the same digest first is accepted only after the winning target is revalidated. Temporary files are removed on success or failure.

Concurrent writers of identical bytes may converge. A concurrent or pre-existing mismatching target fails rather than being repaired heuristically.

This strengthens the implementation of the one authoritative store without changing its on-disk layout.

## Cache compatibility

`CacheReceipt` remains in `cache.py` with its current fields and semantic meaning.

`ContentAddressedCache` remains the acquisition-facing abstraction. Its public `put_bytes(source_id, revision, upstream_path, payload, *, rights_status)` behavior remains compatible:

1. delegate exact payload storage to `ContentStore.put_bytes`;
2. derive the same receipt path from `source_id`, `revision`, and `upstream_path`;
3. preserve the current pinned-path immutability check;
4. preserve an existing receipt byte-for-byte on repeated identical acquisition;
5. create `retrieved_at` only when a new receipt is first written.

Existing cache directories require no migration. Existing object and receipt paths remain valid.

Existing acquisition adapters require no semantic changes and continue to instantiate `ContentAddressedCache(cache_root)`.

`ContentAddressedCache.object_path(sha256)` remains as a compatibility delegation to `ContentStore.object_path(sha256)` so existing tests and consumers do not need a flag-day migration.

## Ingestion input contract

`ObservedArtifactCandidate` represents one source observation that an already-cached payload is a puzzle or solution artifact associated with a canonical repository puzzle.

Required fields:

- `artifact_kind`: `puzzle` or `solution`;
- `puzzle_id`: canonical repository conceptual puzzle ID;
- `artifact_format`: source artifact format such as `puzzle` or `solution`;
- `artifact_receipt`: the `CacheReceipt` for the exact puzzle or solution bytes.

Optional fields:

- `evidence_receipt`: a second `CacheReceipt` for source metadata that supports the observation; absent means the artifact receipt itself is the evidence object;
- `source_object_id`: stable selector within the evidence source object when needed;
- `source_url`;
- `author`;
- `claimed_cost`;
- `claimed_cycles`;
- `claimed_area`;
- `claimed_instructions`.

The candidate contains no local source path and no raw payload bytes.

The artifact receipt is authoritative for:

- exact artifact SHA-256;
- exact artifact byte length;
- artifact source ID/revision/upstream path;
- source-level rights governing the artifact bytes;
- artifact retrieval timestamp.

The evidence receipt is authoritative for the source claim's:

- source ID;
- pinned source revision;
- upstream source path;
- evidence-object SHA-256 and byte length;
- evidence-object rights status;
- stable retrieval timestamp.

When `evidence_receipt` is absent, those evidence fields come from `artifact_receipt`.

This distinction matters for sources such as `om-leaderboard`, where exact solution bytes live in a `.solution` source object but claimed score metadata lives in an adjacent `.json` source object. The generic ingestion layer preserves both receipts instead of attributing JSON-derived claims to the solution source path.

Attached evidence must come from the same `source_id` and `revision` as the artifact receipt. Cross-source joins are represented as separate candidates rather than by combining one source's artifact receipt with another source's metadata receipt.

Ingestion never synthesizes `retrieved_at` and never substitutes build-clock time.

## Ingestion validation

Before producing artifact facts for a candidate, ingestion validates the artifact object with:

`ContentStore.require(candidate.artifact_receipt.sha256, candidate.artifact_receipt.byte_length)`

If a distinct evidence receipt is present, ingestion also validates that evidence object with `ContentStore.require`.

This establishes that every exact source object relied upon by ingestion still exists and still matches its acquisition receipt.

Ingestion must not call `ContentStore.put_bytes`, open adapter snapshot files, inspect file modification times, or maintain another object directory.

An artifact receipt identity is:

`(source_id, revision, upstream_path)`

Within one ingestion operation, one artifact receipt identity may map to only one semantic association `(artifact_kind, puzzle_id, artifact_format, sha256, byte_length)`. Reusing it with conflicting semantic association fails closed.

An evidence assertion identity is:

`(source_id, revision, upstream_path, source_object_id)`

One evidence assertion identity may support only one artifact ID within one ingestion operation. If one source object intentionally describes multiple artifacts, orchestration must provide stable distinct `source_object_id` selectors for those assertions.

## Artifact identity

Artifact identity is deterministic from semantic namespace plus exact SHA-256:

- puzzle artifact: `om.puzzle-artifact.sha256.<64-hex-digest>`;
- solution artifact: `om.solution.sha256.<64-hex-digest>`.

No source name, source path, timestamp, author, score, local directory, collection ID, or mutable counter participates in artifact identity.

Exact bytes are the v1 deduplication boundary. No parsing, newline normalization, decompression, semantic equivalence, machine-behavior comparison, or reserialization participates in deduplication.

Puzzle and solution namespaces remain distinct even if identical physical bytes are observed in both roles. Both may reference the same `StoredObject`.

## Ingestion outputs

### `ArtifactRecord`

A frozen artifact fact contains:

- `artifact_kind`;
- `artifact_id`;
- `puzzle_id`;
- `sha256`;
- `byte_length`;
- `artifact_format`;
- aggregate `rights_status`;
- `object_key` from the artifact `StoredObject`.

It contains no source-specific fields, retrieval timestamp, claimed metric, verifier field, normalized representation, or absolute local path.

### `ArtifactProvenance`

Provenance is emitted per exact source object rather than collapsing artifact bytes and metadata evidence into one row.

Every candidate emits one artifact-source provenance fact from `artifact_receipt`. It contains:

- `artifact_id`;
- `puzzle_id`;
- `source_role = "artifact"`;
- artifact receipt source ID, revision, and upstream path;
- artifact receipt retrieval timestamp and rights status;
- `observed_sha256` equal to the artifact receipt SHA-256;
- `source_evidence_sha256` and `source_evidence_byte_length` equal to the artifact receipt's own hash and length.

When the evidence receipt is distinct from the artifact receipt, ingestion emits a second evidence provenance fact. It contains:

- the same `artifact_id` and `puzzle_id`;
- `source_role = "evidence"`;
- evidence receipt source ID, revision, and upstream path;
- optional `source_object_id`, source URL, and author;
- evidence receipt retrieval timestamp and rights status;
- source-claimed metrics;
- `observed_sha256` equal to the artifact receipt SHA-256;
- `source_evidence_sha256` and `source_evidence_byte_length` from the evidence receipt.

When the artifact receipt itself is also the evidence object, ingestion emits only the artifact-source provenance fact and attaches the optional source object/URL/author/claimed fields to that fact. It does not emit a duplicate evidence row for the same receipt.

The source-evidence hash and byte length retain auditability when claims come from metadata bytes distinct from the artifact bytes. A later projection may omit fields not present in the current observation schema, but ingestion does not discard them.

These are internal facts suitable for later projection into the existing observation schema. They are not themselves release JSONL.

### `IngestionResult`

`IngestionResult` contains deterministic tuples of artifact records and provenance facts.

Returned order is stable and independent of candidate iteration order, cache root location, working directory, or wall-clock time.

## Deduplication and conflicts

Candidates with the same `artifact_kind`, canonical `puzzle_id`, digest, and compatible format converge onto one artifact record while retaining all distinct provenance assertions.

Different digests always remain different artifact records.

Fail closed when one semantic artifact digest is associated with:

- different canonical puzzle IDs in the same artifact namespace;
- conflicting artifact formats;
- inconsistent byte lengths or content-store keys;
- an invalid, missing, non-file, or corrupt stored object.

Fail closed when one artifact receipt identity is reused with conflicting semantic association or one evidence assertion identity is reused as contradictory evidence for multiple artifact IDs.

Exact duplicate provenance facts may collapse. Provenance differing in source role, source identity, revision, upstream path, source object selector, retrieval event, author, source URL, evidence hash, evidence length, evidence rights, or claimed metrics remains distinct.

## Rights aggregation

Artifact-level rights are folded from `artifact_receipt.rights_status`, because that status governs publication of the exact puzzle/solution bytes.

The fold is deterministic and conservative:

1. `local_fetch_only` if any artifact receipt is `local_fetch_only`;
2. otherwise `unknown` if any artifact receipt is `unknown`;
3. otherwise `redistributable`.

Each provenance fact separately preserves the rights status of its own source receipt unchanged.

Unknown rights values fail closed rather than being coerced.

This fold is publication-safety policy, not a claim that sources agree about licensing.

## Source-claimed metrics

Claimed cost, cycles, area, and instruction counts remain provenance-only source facts.

Ingestion does not verify them, recompute them, choose a preferred claim, or copy them into computed solution fields.

For `om-leaderboard`, later orchestration may parse the already-cached adjacent JSON source fact, supply its JSON receipt as `evidence_receipt`, and attach its claims to a candidate whose `artifact_receipt` is the corresponding solution receipt. Ingestion then preserves one provenance fact for the `.solution` bytes and a second provenance fact for the `.json` claims. That source-specific association is deliberately outside this generic ingestion module.

An orphan metadata receipt without a corresponding exact artifact receipt cannot produce an artifact candidate in this slice. It remains acquisition evidence for future source-specific reconciliation.

## Release and verifier boundaries

This slice does not write `puzzles.jsonl`, `solutions.jsonl`, `observations.jsonl`, or `normalized.jsonl`.

It does not change release schemas.

It does not invoke a verifier or create placeholder verifier revisions, profiles, verification booleans, or computed metrics.

A later verifier layer can consume `ArtifactRecord` plus `ContentStore.require(...)` to access exact puzzle/solution bytes. Verification produces derived facts without mutating artifact identity or provenance.

A later materialization layer can combine artifact facts, provenance, verification, and normalization into the existing release inputs.

## Adapter boundary

Existing acquisition adapters continue to acquire source data and write source receipts through `ContentAddressedCache`.

No concrete adapter is imported by `ingestion.py`.

`om-archive` and `om-leaderboard` acquisition behavior remains unchanged by this slice. Their existing tests are regression gates for the storage refactor.

The adapter stubs for sources not yet acquired remain outside this design; this work does not revive the historical adapter implementation branch.

## Determinism

Given the same cache objects, receipts, canonical puzzle associations, and optional source facts, ingestion produces identical logical records regardless of:

- cache root location;
- candidate iteration order;
- operating directory;
- wall-clock build time.

No absolute local path enters artifact IDs, artifact records, provenance facts, sort keys, or release-facing values.

Receipt `retrieved_at` may differ between independent first-time network acquisitions because it records the actual acquisition event. Repeated offline materialization from the same persisted receipt is deterministic and must not rewrite that timestamp.

## Error model

`ContentStore` has a typed integrity/storage error derived from the repository's corpus error base.

Ingestion has a typed `ArtifactIngestionError` for semantic association conflicts or invalid candidate data.

Content corruption detected through `ContentStore.require` propagates as the content-store integrity error rather than being hidden or translated into successful partial ingestion.

Errors should identify stable digest/source/puzzle context where useful without requiring absolute local paths in canonical data.

## File structure

Planned production files:

- create `src/opus_corpus/content_store.py`: exact-byte storage and integrity only;
- modify `src/opus_corpus/cache.py`: acquisition receipts delegating exact-byte storage;
- create `src/opus_corpus/ingestion.py`: receipt-based artifact/provenance facts and deterministic grouping.

Planned tests:

- extend `tests/test_cache.py` for compatibility and delegation behavior;
- create `tests/test_content_store.py` for exact object storage/integrity behavior;
- create `tests/test_ingestion.py` for receipt-based artifact semantics;
- retain existing adapter tests unchanged as regression coverage unless a purely mechanical import expectation requires adjustment.

## Testing requirements

### Content store

Tests must prove:

1. `put_bytes` preserves the existing `objects/sha256/<2>/<62>` layout;
2. identical bytes are idempotent and produce one object identity;
3. distinct bytes produce distinct objects;
4. `require` accepts a valid existing object;
5. `require` rejects missing objects;
6. `require` rejects corrupt bytes under a digest path;
7. `require` rejects byte-length mismatch;
8. invalid digest input fails explicitly;
9. concurrent/existing-target handling never silently overwrites mismatching content;
10. temporary publication files do not remain after success or failure.

### Cache compatibility

Tests must prove:

1. current `ContentAddressedCache.put_bytes` call sites remain valid;
2. receipt paths are unchanged;
3. repeated identical acquisition returns the existing receipt unchanged;
4. changed payload for one pinned source path still fails;
5. existing object paths returned through `ContentAddressedCache.object_path` are unchanged;
6. a pre-existing valid cache directory can be read without migration.

### Ingestion

Tests must prove:

1. stable puzzle and solution artifact IDs from artifact receipt digests;
2. exact-byte duplicate solution observations converge without losing provenance;
3. exact-byte duplicate puzzle observations converge without losing provenance;
4. different digests never deduplicate;
5. puzzle and solution namespaces remain distinct while sharing one stored object when bytes match;
6. conservative artifact-byte rights aggregation and unchanged per-source provenance rights;
7. source-claimed metrics remain provenance-only;
8. adjacent metadata evidence produces distinct artifact-source and evidence-source provenance facts preserving both source paths and both exact hashes/lengths;
9. same-receipt evidence produces one provenance fact rather than a duplicate pair;
10. exact duplicate provenance assertions collapse while distinct assertions remain;
11. candidate order and cache-root location do not affect logical output;
12. same digest mapped to different puzzle IDs fails closed;
13. conflicting artifact formats fail closed;
14. the same artifact receipt identity mapped inconsistently fails closed;
15. the same evidence assertion identity used contradictorily fails closed;
16. evidence from a different source ID or revision than its artifact receipt fails closed;
17. missing/corrupt artifact or evidence objects fail through the shared content-store integrity path.

### Repository acceptance

The repository CI-equivalent suite must remain green:

- Ruff;
- full pytest suite;
- frozen collection validation;
- tiny release build/validate/stage.

Existing `om-archive` and `om-leaderboard` acquisition tests are specifically required to remain green without semantic rewrites.

## Non-goals

This slice does not implement:

- new network acquisition sources;
- adapter-specific receipt discovery/orchestration;
- parsing om-leaderboard JSON into candidates;
- official-game local acquisition;
- verifier execution;
- verifier result schemas;
- puzzle or solution parsing;
- normalized puzzle/solution generation;
- observation ID generation or release observation projection;
- release JSONL materialization;
- canonical puzzle-artifact selection when multiple puzzle byte artifacts exist;
- release schema changes;
- semantic-equivalence deduplication;
- Pareto/frontier derivation;
- Hugging Face publication changes;
- migration or duplication of the historical PR #12 storage implementation.

## Acceptance criteria

The slice is complete when:

1. one `ContentStore` is the sole implementation of exact-byte object layout and integrity verification;
2. `ContentAddressedCache` preserves current public acquisition behavior and cache compatibility while delegating byte storage;
3. ingestion consumes persisted artifact/evidence `CacheReceipt` facts instead of source filesystem payloads;
4. ingestion validates every artifact and evidence object it relies upon through `ContentStore.require`;
5. deterministic artifact IDs and exact-byte deduplication preserve all distinct provenance;
6. metadata-derived claims retain both the exact artifact source receipt and the exact evidence receipt they came from;
7. artifact-byte rights and per-source provenance rights remain separate source facts with no invented verifier state;
8. semantic conflicts and content corruption fail closed;
9. existing acquisition adapters and release behavior remain unchanged;
10. repository validation is green;
11. no second content-addressed publisher, object layout, or ingestion-side byte cache exists.
