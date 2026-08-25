# Deterministic solution views

Status: **Implemented v1**

WP-13 defines the first research-grade derived views over canonical release solution rows. These views are generated projections. They are not a second solution store, a new source of corpus truth, or a place for manual curation.

## Authority boundary

The input is the existing `solutions` release-row contract produced from canonical artifacts and verifier facts. Canonical artifacts, provenance, and verification records remain authoritative. A solution view may select and reorder release rows, but it must not reinterpret, repair, annotate, or replace their payload.

If a view is stale, regenerate it. Do not maintain it by hand.

## V1 predicates

The v1 contract defines exactly three views:

| View | Predicate |
| --- | --- |
| `all-verified` | `verified is true` |
| `vanilla-constructible` | `verified is true` and `vanilla_constructible is true` |
| `record-eligible` | `verified is true` and `record_eligible is true` |

An unverified row is excluded from every view even if another predicate field is `true`. An explicit `null` predicate is unknown and therefore does not satisfy a narrower `true` predicate. Missing fields, schema-invalid rows, non-mapping rows, and duplicate `solution_id` values fail closed rather than being silently omitted or repaired.

Changing these predicates is a view-contract change. It must not silently redefine v1.

## Determinism

`derive_solution_views()` validates every input row against the existing `solutions` release schema, requires unique solution identities, and then applies the predicates above. Rows are ordered by the existing canonical solution sort key, `(puzzle_id, solution_id)`, so caller input order cannot affect a view.

Each returned view owns independent row mappings. Mutating one in-memory view cannot mutate another view or the caller's input row.

`materialize_solution_views()` writes three JSONL files:

```text
all-verified.jsonl
vanilla-constructible.jsonl
record-eligible.jsonl
```

Each row is written with the repository's canonical JSON encoding and a trailing newline. Empty views are represented by empty files. The destination directory is published through the existing transactional directory-publication primitive, so a failed derivation or write does not intentionally expose a partially populated replacement.

Given equivalent valid input rows, the materialized bytes are independent of input order.

## Scope boundary

V1 deliberately does not implement Pareto frontiers, best-known metric views, human-versus-machine classification, benchmark selections, model-oriented puzzle serialization, or benchmark execution. Those require separate explicit predicates or protocols and should remain downstream deterministic projections over the canonical corpus.
