# Model-oriented puzzle serialization

Status: **Implemented v2**

The benchmark-facing puzzle text is a deterministic projection of canonical semantic `PuzzleDefinition` state. It is not another puzzle schema, corpus store, artifact decoder, or normalization layer.

## Authority boundary

`PuzzleDefinition` is the semantic authority for puzzle meaning. Exact `.puzzle` bytes remain separate `PuzzleArtifact` evidence used where byte identity matters, especially verification. The serializer validates a `PuzzleDefinition`, selects solve-relevant semantic fields, and renders them. If the semantic definition changes, regenerate the serialization rather than editing serialized text.

Artifact and provenance lineage are deliberately excluded from model input:

- `source_observation_ids`
- `puzzle_artifact_ids`

Those fields remain on the canonical `PuzzleDefinition`. The payload keeps both `puzzle_definition_id` and `puzzle_id` so benchmark input can be bound to the exact semantic definition evaluated without exposing acquisition bookkeeping to the model.

## V2 identity

The implementation is `ModelPuzzleTextSerializer` in `opus_corpus.serialization`.

```text
format_name = opus-magnum-puzzle-text
version = 2
header = OPUS_MAGNUM_PUZZLE_TEXT_V2
```

The serializer version is an implementation identity, not a constructor option. A representation change requires a new declared version and corresponding tests rather than relabeling the existing implementation.

## V2 fields and order

After the header, v2 emits exactly these fields in this order:

```text
puzzle_definition_id
puzzle_id
allowed_parts
allowed_instructions
reagents
products
output_scale
target_output_count
production
production_constraints
```

Each line is `name=<canonical-json-value>`. Field order is explicit. JSON object keys are sorted, compact separators are used, and JSON string escaping is preserved. Unicode NEL, line separator, and paragraph separator characters are emitted as `\u0085`, `\u2028`, and `\u2029` so string content cannot create extra text lines. The serialization ends with a newline.

Example shape:

```text
OPUS_MAGNUM_PUZZLE_TEXT_V2
puzzle_definition_id="om.puzzle-definition.sha256.<digest>"
puzzle_id="om.puzzle.0001"
allowed_parts=["arm1","bonder"]
allowed_instructions=["drop","grab"]
reagents=[...]
products=[...]
output_scale=1
target_output_count=6
production=false
production_constraints=null
```

The behavior contract is pinned in `tests/test_puzzle_text_serialization.py`.

## Determinism boundary

`PuzzleDefinition` construction owns semantic canonicalization. The serializer does not reinterpret raw puzzle bytes, merge evidence, derive semantic claims, or maintain its own normalized-puzzle representation. Given the same validated `PuzzleDefinition` and serializer version, output is byte-for-byte identical regardless of input mapping insertion order.

This separation prevents a second semantic path:

```text
source evidence -> PuzzleDefinition -> model text
exact bytes     -> PuzzleArtifact  -> verifier
```

A semantic definition may exist without an exact artifact. Multiple byte-distinct artifacts may also support the same semantic definition. Neither case changes the model-facing semantic representation.

## Failure behavior

Invalid `PuzzleDefinition` input fails closed with `PuzzleSerializationError`. Missing semantic fields, malformed molecule structure, an invalid semantic identity, or other definition-schema violations are not repaired silently. Values that cannot be represented safely as UTF-8 JSON also fail rather than being coerced.

The serializer does not accept raw `.puzzle` bytes. Raw-byte benchmark input is a separate benchmark input profile under `docs/benchmark-protocol.md`.

## Downstream use

The Solve harness should record `format_name`, `version`, and the semantic puzzle identity used for the run. It should invoke the serializer over canonical `PuzzleDefinition` state and should not maintain checked-in prompt copies or a parallel normalized-puzzle dataset.
