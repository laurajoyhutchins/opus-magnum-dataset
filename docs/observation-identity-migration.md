# Observation identity migration: canonical schema 0.2

The previous canonical observation schema required `retrieved_at`. The
acquisition wall clock changed an observation ID when identical bytes were
fetched into a fresh cache, and puzzle-semantic evidence referenced that ID.

Starting with `corpus_schema_version = "0.2"`, canonical observation rows do
not include `retrieved_at`. A source's pinned revision, exact source byte/hash
identity, source path, evidence digest, rights, and importer version retain
their previous identity roles. Acquisition time remains in the
`CacheReceipt.retrieved_at` operational/audit record only. Cache receipts are
**not** interchangeable with canonical observations.

## Deterministic migration

1. Read back and verify the original source revision, exact bytes, cache
   receipt digest, permissions/rights and importer inputs. Fail closed if any
   pinned source fact is unavailable or differs.
2. Re-run the normal materializers against those source facts. Do not edit
   stored observation IDs by search/replace and do not copy historical clocks
   into the new rows.
3. Rebuild PuzzleDefinition source-observation references, release records,
   and all downstream manifests/digests from the resulting new observation
   identities. Validate the complete newly built release as schema 0.2.
4. Retain old schema-0.1 materializations as historical evidence only; they
   are not admitted by the current observation schema. Do not automatically
   relabel legacy release receipts as schema 0.2.

No arbitrary fallback timestamp is synthesized, and no new authority store
is introduced. The separately retained acquisition audit trail can still
report when a fetch happened, but changing that time cannot affect a
canonical observation, semantic puzzle, or rebuilt release.
