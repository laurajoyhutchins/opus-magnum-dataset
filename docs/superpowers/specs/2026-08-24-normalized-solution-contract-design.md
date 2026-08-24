# Normalized Solution Contract Design

## Status

Approved as PR 2 in the downstream materialization stack. This PR is stacked on the verified canonical Verification contract in PR #13.

## Goal

Turn the existing permissive normalized-solution release shape into a useful structural contract and add a narrow, deterministic `SolutionNormalizer` seam, without implementing an Opus Magnum `.solution` parser.

## Stack position

```text
main with #6 + #9
  -> #13 verification contract
    -> normalized-solution contract
      -> deterministic materialization pipeline
```

This branch must not add source acquisition, simulator integration, parser implementation, or a second representation authority.

## Representation boundary

A normalized solution is derived state over one exact `SolutionArtifact`. It is not artifact identity and is not verification evidence. The exact source solution remains identified by `solution_id`; a normalized record identifies the puzzle context used to interpret it and the normalizer version that produced the projection.

Serializers remain deterministic projections over normalized records through the existing `NormalizedSerializer` seam. This PR does not add a model-specific DSL or a second maintained text representation.

## Deterministic normalized identity

`normalized_solution_id` is derived from exactly:

- `solution_id`
- `puzzle_id`
- `normalizer_version`

The identity payload is serialized with the repository's existing `canonical_json_bytes()` helper, hashed with SHA-256, and emitted as `om.normalized-solution.<hex-digest>`.

Normalized output contents are not part of the identity. A change in normalizer behavior must therefore carry a new `normalizer_version`.

## Hardened normalized-solution schema

Harden `schemas/normalized.schema.json` in place because it is already the release schema for normalized solution rows. The outer record remains strict and keeps the current top-level fields:

- `normalized_solution_id`
- `solution_id`
- `puzzle_id`
- `normalizer_version`
- `parts`
- `tracks`
- `programs`
- `summaries`

### Parts

Each part is a strict object with:

- `part_id`: stable within the solution record;
- `type`: source-normalized part type string;
- `x`, `y`: integer axial-grid coordinates;
- `rotation`: integer orientation from 0 through 5;
- `parameters`: an explicit object for type-specific parameters.

The `parameters` object is deliberately extensible. It is the only unconstrained nested object in the structural core so future parser work can carry proven type-specific fields without weakening the common part shape.

### Tracks

Each track is a strict object with:

- `track_id`;
- `coordinates`: one or more strict `{x, y}` axial coordinate objects.

This keeps track geometry separate from ordinary parts.

### Programs

Each program is a strict object with:

- `arm_id`: the part identifier of the programmed arm;
- `instructions`: ordered strict instruction objects.

Each instruction contains:

- `cycle`: integer >= 0;
- `opcode`: non-empty normalized opcode string.

Opcode vocabulary is intentionally not frozen in this stub. The eventual parser must define/version the normalization vocabulary based on actual game-format semantics rather than guesses in this interface PR.

### Summaries

`summaries` is a strict object containing deterministic, inexpensive projections:

- `part_count`
- `track_count`
- `track_hex_count`
- `program_count`
- `instruction_count`
- `part_type_histogram`
- `opcode_histogram`

Counts are non-negative integers. Histogram values are non-negative integers. These summaries are generated from structural content and must never become separately maintained authority.

## Python interface

Add `src/opus_corpus/normalization.py` with only solution-normalization domain types and deterministic helpers:

```python
NormalizedSolutionRecord = Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class SolutionNormalizationInput:
    solution_id: str
    puzzle_id: str
    solution_bytes: bytes

@runtime_checkable
class SolutionNormalizer(Protocol):
    version: str
    def normalize(self, value: SolutionNormalizationInput) -> NormalizedSolutionRecord: ...
```

Add:

```python
def normalized_solution_id(
    *, solution_id: str, puzzle_id: str, normalizer_version: str
) -> str: ...
```

The protocol consumes bytes directly because normalization belongs to offline deterministic materialization over pinned cached artifacts. It performs no network access.

## Fixture migration

Update `fixtures/tiny-corpus/normalized.jsonl` to satisfy the hardened schema. Keep it tiny but structurally representative: one arm part, one program/instruction, no tracks, and complete deterministic summary fields.

The fixture remains test data, not a hand-maintained production normalized corpus.

## Tests

Add `tests/test_normalization.py` proving:

1. a structurally representative normalized record validates;
2. unknown part fields are rejected;
3. invalid rotation values are rejected;
4. negative instruction cycles are rejected;
5. summary objects reject unknown fields;
6. normalized IDs are deterministic;
7. changing solution, puzzle context, or normalizer version changes the ID;
8. the ID interface excludes normalized output/result fields;
9. `SolutionNormalizer` is a runtime-checkable protocol with the expected seam;
10. a tiny fake normalizer can satisfy the protocol without importing parser, adapter, or verifier code.

## Compatibility

The top-level release config name and existing `NormalizedSerializer.serialize_solution()` interface remain unchanged. This is a schema hardening and producer seam, not a new release configuration.

## Non-goals

No `.solution` parsing, `omsim` integration, source acquisition, verification, metric computation, semantic-equivalence clustering, model-specific text DSL, release orchestration, or hand-maintained normalized index.

## Acceptance criteria

The hardened schema, updated tiny fixture, deterministic ID helper, normalization input/protocol seam, and focused contract tests exist; the entire existing validation workflow passes; and no parser implementation or acquisition behavior is introduced.
