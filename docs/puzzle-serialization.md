# Model-oriented puzzle serialization

Status: **Implemented v1**

WP-13 defines the first benchmark-facing puzzle input representation. It is a deterministic projection over a canonical normalized puzzle record. It is not another puzzle schema, corpus store, or normalization layer.

## Authority boundary

Canonical normalized puzzle data remains authoritative. The serializer validates its input against `normalized-puzzle.schema.json`, selects solve-relevant fields, and renders them. If the source record changes, regenerate the serialization rather than editing serialized text.

The v1 model payload deliberately excludes corpus lineage and materialization metadata:

- `normalized_puzzle_id`
- `puzzle_artifact_id`
- `normalizer_version`

Those fields remain available in canonical corpus state and benchmark manifests. The payload retains `puzzle_id` so model input and benchmark result rows can be associated with the evaluated puzzle.

## V1 identity

The implementation is `ModelPuzzleTextSerializer` in `opus_corpus.serialization`.

```text
format_name = opus-magnum-puzzle-text
version = 1
header = OPUS_MAGNUM_PUZZLE_TEXT_V1
```

The serializer version is an implementation identity, not a constructor option. A representation change requires a new declared version and corresponding golden tests rather than relabeling the existing implementation.

## V1 fields and order

After the header, v1 emits exactly these fields in this order:

```text
puzzle_id
allowed_parts
reagents
products
constraints
```

Each line is `name=<canonical-json-value>`. JSON object keys are sorted, compact separators are used, string escaping follows JSON rules, and non-finite numeric values are rejected rather than emitted as non-standard JSON. Unicode NEL, line separator, and paragraph separator characters are emitted as `\u0085`, `\u2028`, and `\u2029` escapes so JSON string content cannot create additional text lines. The complete serialization ends with a newline.

Example shape:

```text
OPUS_MAGNUM_PUZZLE_TEXT_V1
puzzle_id="om.puzzle.0001"
allowed_parts=["arm1","bonder"]
reagents=[...]
products=[...]
constraints={}
```

The literal full output for the test fixture is pinned in `tests/test_puzzle_text_serialization.py` as the v1 golden contract.

## Determinism boundary

Mapping insertion order cannot change the serialized bytes because field order is explicit and nested mapping keys use canonical JSON ordering.

The serializer intentionally does **not** reorder `allowed_parts`, reagent/product molecules, atoms, or bonds. Ordering of canonical normalized arrays belongs to normalization. Reordering them in the serializer would quietly create a second semantic-normalization path. Given the same canonical normalized puzzle record and serializer version, output is byte-for-byte identical.

Open-ended values such as `constraints` must already use JSON-native Python shapes: dictionaries with string keys, lists, strings, finite JSON numbers, booleans, or null. Python-only values are rejected rather than coerced. For example, integer dictionary keys are not stringified and tuples are not converted to arrays. Strings and object keys must also be valid UTF-8 text. This keeps distinct malformed Python inputs from collapsing onto the same serialized representation.

## Failure behavior

Schema-invalid normalized puzzle records fail closed with `PuzzleSerializationError`. Missing solve fields, unknown root fields, malformed molecule structure, and other schema violations are not silently repaired or omitted. Values that cannot be represented one-to-one as standards-compliant UTF-8 JSON also fail closed, including `NaN`, infinities, non-string object keys, Python-only container types, lone Unicode surrogates, and cyclic lists or dictionaries.

The serializer does not accept raw `.puzzle` bytes. Raw-byte benchmark input is a separate benchmark input profile under `docs/benchmark-protocol.md`.

## Downstream use

The Solve harness should record both `format_name` and `version` in benchmark identity and should obtain model input by invoking this serializer over canonical normalized puzzle data. It should not maintain checked-in copies of serialized puzzle prompts as another dataset.
