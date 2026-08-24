# Source Adapter Stubs Design

## Goal

Introduce the smallest stable source-adapter surface needed to begin deterministic acquisition work without prematurely implementing cache, network, parsing, verification, or release orchestration.

## Scope

Create six source-specific adapter stubs for the source classes already identified in the repository documentation:

- `leaderboard-bot`
- `om-archive`
- `om-leaderboard`
- `omsim`
- `molecule-db`
- locally acquired official game puzzle artifacts

The stubs do not acquire data yet. They establish source identity, pinned revision metadata where one exists, and an explicit `fetch` boundary that accepts a validated `CollectionDefinition` plus a filesystem cache root.

## Contract

`SourceAdapter` is a small concrete base class rather than a broad orchestration framework. It exposes immutable source metadata and a `fetch(collection, cache_root)` method. The default implementation raises `AdapterNotImplementedError`, so every stub fails explicitly until source-specific acquisition is implemented.

Each adapter module exports one class. A registry maps stable `source_id` values to adapter classes so future CLI or acquisition software can select adapters without hard-coded conditionals.

The contract intentionally does not define canonical-record emission, verification, normalization, rights reconciliation, HTTP clients, Git clients, or content-addressed-cache internals. Those interfaces should be added only when their first real implementation exists.

## Source metadata

Pinned revisions come from `docs/source-inventory.md` where applicable:

- `leaderboard-bot`: `ca40dee95da584270eb3be1c4b74e2be63afa7e6`
- `om-archive`: `44006a0eeb0051337640443d1b0576ea24c983f6`
- `om-leaderboard`: `0cfd371ef66cf94eac3f7a7a06bc9ab959495576`
- `omsim`: `758f4a4b4c9e24f50294801da774a0960c922bab`
- `molecule-db`: `6f3cd8068428ef96ac6426d092c3523da359ec76`
- `official-game`: no repository revision; exact local artifact hashes will become the immutable identity when acquisition is implemented

## Error behavior

Calling `fetch` on any stub raises `AdapterNotImplementedError` containing the source ID. This is deliberate fail-closed behavior: an adapter cannot silently report success or emit partial source state before its acquisition semantics are implemented.

## Testing

Contract tests verify:

1. the registry contains exactly the six expected source IDs;
2. each registered adapter has stable source metadata;
3. every stub is constructible and conforms to the base type;
4. each unimplemented `fetch` call fails with `AdapterNotImplementedError`.

No tests mock upstream services because no network behavior is part of this slice.
