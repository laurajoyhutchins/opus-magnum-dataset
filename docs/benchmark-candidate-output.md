# Benchmark candidate-output compilation

Status: **v1 contract for Solve v0.1**

The benchmark candidate-output compiler is the single deterministic boundary between raw model text and exact `.solution` bytes. It is repository-owned and independent of model providers, prompts, runners, and verifier implementations.

## Identity

The v1 compiler identity is:

```text
candidate_output_compiler = json-base64-solution
candidate_output_compiler_version = 1
format = om-solution-base64-v1
```

Any semantic change to accepted framing, decoding, or compilation behavior requires a new compiler version. Compiler identity is part of `BenchmarkIdentity`, so such a change alters benchmark identity.

## Accepted envelope

A successful raw response contains exactly one JSON object:

```json
{"format":"om-solution-base64-v1","solution_base64":"<canonical base64>"}
```

Leading and trailing JSON whitespace is allowed. Nothing else is.

The object must contain exactly the two fields above. Duplicate members, missing or extra members, alternate formats, Markdown fences, explanatory prefixes or suffixes, multiple concatenated candidates, invalid base64, non-canonical base64, and empty decoded candidates fail closed.

The compiler decodes `solution_base64` and returns the exact decoded bytes plus the SHA-256 of those exact bytes. It does not normalize, repair, reserialize, parse, or otherwise modify the candidate.

## Failure boundary

Compilation failures are typed `CandidateOutputCompileError` values and map to the WP-15 `output_compile_failed` outcome. Stable v1 detail codes include:

- `not_json`
- `trailing_material`
- `duplicate_field`
- `invalid_envelope`
- `unsupported_format`
- `invalid_base64`
- `noncanonical_base64`
- `empty_candidate`

Compilation success does not mean the decoded bytes are a valid Opus Magnum solution.

After compilation, `parse_candidate_solution` passes the exact bytes to the existing `.solution` parser. `SolutionParseError` therefore remains a downstream `solution_parse_failed` outcome rather than being collapsed into output compilation failure.

When the parsed format exposes a puzzle name, `parse_candidate_solution` compares it with the intended benchmark puzzle name. A mismatch raises `PuzzleSolutionMismatchError` with code `puzzle_solution_mismatch` and maps to the corresponding WP-15 outcome.

Verifier invocation and simulation are outside this module. The v0.1 path is therefore:

```text
raw model text
    ↓ compile_candidate_output
exact bytes + SHA-256
    ↓ parse_candidate_solution
parsed solution + puzzle binding
    ↓ pinned verifier
simulation result and metrics
```

No reasoning agent is permitted to repair malformed candidate output between these stages.