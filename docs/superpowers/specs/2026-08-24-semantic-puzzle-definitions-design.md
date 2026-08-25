# First-Class Semantic Puzzle Definitions Design

## Status

Approved in chat for issue #61 on 2026-08-24. This design deliberately separates the architectural correction from the active WP-12 release PR #58 so exact-artifact verification work can finish without absorbing a semantic-model rewrite.

## Goal

Make the decoded Opus Magnum problem definition the first-class puzzle representation used by research, ML, and release puzzle surfaces.

Exact `.puzzle` bytes remain immutable `PuzzleArtifact` provenance and verifier inputs. They may produce semantic evidence, but neither one selected artifact nor its SHA-256, bytes, or rights status defines semantic puzzle identity.

The implementation must preserve one authoritative corpus path. It must not add a semantic sidecar corpus, hand-maintained semantic index, compatibility layer, second artifact store, or second release authority.

## Current defect

The repository currently has the correct conceptual `Puzzle` / exact-byte `PuzzleArtifact` distinction in `docs/dataset-spec.md`, but two implementation surfaces collapse the distinction again:

- `normalized-puzzle.schema.json` requires `puzzle_artifact_id`, making semantic structure subordinate to one exact byte representation;
- the release `puzzle.schema.json` requires `canonical_puzzle_artifact_id`, `puzzle_sha256`, `puzzle_bytes`, and artifact-level `rights_status`, so the semantic puzzle row is also an artifact publication row.

`puzzle_materialization.py` additionally reduces molecule-db semantics to a `semantic_source_ids` coverage marker rather than materializing a semantic entity. As a result, the corpus can know semantic facts without having a first-class place to represent them.

## Authority model

The canonical puzzle model has three distinct layers.

### Puzzle

`Puzzle` remains the stable repository-defined conceptual identity and collection member. It owns identity and catalog metadata such as:

- `puzzle_id`;
- display name;
- kind;
- collection membership;
- aliases.

It does not own exact bytes and it does not itself encode the full game-level problem definition.

### PuzzleDefinition

`PuzzleDefinition` is the canonical semantic statement of one resolved puzzle problem under a versioned semantic schema.

It owns the information required to state the problem without consuming `.puzzle` bytes:

- semantic schema version;
- `puzzle_id`;
- allowed parts/mechanisms;
- allowed programmable instruction capabilities represented by the puzzle availability mask;
- reagent molecules;
- product molecules;
- atom types and axial coordinates;
- bonds and bond types;
- output scale;
- derived target output count;
- production flag;
- production-specific cabinet, conduit, vial, shrink, and isolation constraints.

Display names, creators, source filenames, byte hashes, raw availability masks, and serialization-specific details are not semantic identity unless they affect the actual game problem.

### PuzzleArtifact

`PuzzleArtifact` remains one exact immutable byte representation with its existing identity, SHA-256, byte length, format, rights status, source observations, and `ContentStore` object.

One `PuzzleDefinition` may be supported by zero, one, or multiple exact artifacts. Two byte-distinct artifacts that decode to the same semantic problem do not create two semantic problem definitions.

Verification remains explicitly `PuzzleArtifact + SolutionArtifact + verifier/profile`. No verification API is changed to accept `PuzzleDefinition` in place of exact bytes.

## Semantic schema

Replace `normalized-puzzle.schema.json` rather than preserving it as a parallel abstraction. The new packaged schema is `puzzle-definition.schema.json`.

The top-level record is strict and contains:

- `puzzle_definition_id`;
- `schema_version`;
- `puzzle_id`;
- `allowed_parts`;
- `allowed_instructions`;
- `reagents`;
- `products`;
- `output_scale`;
- `target_output_count`;
- `production`;
- `production_constraints`;
- `source_observation_ids`;
- `puzzle_artifact_ids`.

`source_observation_ids` and `puzzle_artifact_ids` are provenance attachments. They are not included in `puzzle_definition_id`.

### Molecules

A molecule is represented canonically as ordered semantic content rather than parser object identity.

Each atom contains:

- `atom_type` using a versioned canonical vocabulary;
- axial `q`, `r` coordinates.

Atoms are sorted deterministically by `(q, r, atom_type)`. Equal atom entries remain repeated entries because atom multiplicity is semantic content; canonicalization must not silently deduplicate them.

Each bond contains:

- canonical endpoint coordinates `a_q`, `a_r`, `b_q`, `b_r`;
- `bond_types`, a sorted unique list drawn from the decoded bond-bit vocabulary.

Bond endpoints are normalized lexicographically so reversing an edge in a source does not change semantic identity. Bonds are sorted deterministically after endpoint normalization. A bond referring to a coordinate absent from the molecule fails closed. Equal bond entries remain repeated only when the decoded source itself contains repeated bond entries; the canonicalizer never invents or removes multiplicity.

Reagents and products retain multiplicity and are ordered by a canonical molecule-content key rather than source ordering. Semantically identical repeated molecules remain repeated entries.

This intentionally separates problem semantics from binary input/output index ordering. Exact solution verification continues against an exact `PuzzleArtifact`, so any serialization-specific index relationship remains an artifact/verifier concern rather than semantic identity.

### Allowed capabilities

The puzzle availability mask is decoded into semantic capability names. Because the mask gates both placed parts and programmable operations, the definition records them separately as `allowed_parts` and `allowed_instructions`.

The canonical vocabulary is derived and tested against the pinned omsim decoder behavior. A set availability bit with no known semantic mapping fails closed instead of being dropped or copied through as an unexplained raw integer.

### Output target

The raw format-3 `output_scale` is semantic because it changes the required output count and repeating-output behavior. The definition records both:

- `output_scale`;
- `target_output_count`, deterministically derived as `6 * output_scale` under the pinned game/verifier semantics.

The reconciler validates this invariant rather than accepting independently supplied contradictory values.

### Production constraints

`production_constraints` is `null` when `production` is false. When true, it is a strict object containing:

- `shrink_left`;
- `shrink_right`;
- `isolate_inputs_from_outputs`;
- canonicalized cabinets with position and cabinet type;
- canonicalized conduits with both starting positions and relative conduit hexes;
- canonicalized vials with position, style, and count.

Unknown future production fields require an explicit schema-version change. They are not placed into a free-form `constraints` object.

## Semantic identity

`puzzle_definition_id` is content-derived and independent of source ordering, evidence ordering, exact artifact identity, and binary serialization identity.

The identity body contains exactly:

- `schema_version`;
- `puzzle_id`;
- the complete canonical semantic content from `allowed_parts` through `production_constraints`.

It excludes:

- `source_observation_ids`;
- `puzzle_artifact_ids`;
- source revisions/paths;
- artifact SHA-256 values;
- producer implementation version.

The identity body is encoded with the repository's existing canonical JSON helper and SHA-256. IDs use the prefix `om.puzzle-definition.sha256.`.

Including `puzzle_id` prevents two distinct repository puzzle identities with accidentally identical problem content from collapsing into one entity. Excluding producer version means a corrected or independent producer that yields exactly the same canonical semantics also yields the same definition identity.

## Evidence and reconciliation boundary

Add one deterministic semantic reconciliation path. Producers emit typed `PuzzleDefinitionEvidence`; only the reconciler emits canonical `PuzzleDefinition` records.

`PuzzleDefinitionEvidence` is an in-memory/materialization boundary, not a new persisted corpus store. Each evidence value contains:

- `puzzle_id`;
- an evidence provenance reference sufficient to derive or link a canonical `Observation`;
- optional supporting `puzzle_artifact_id`;
- the semantic fields actually known by that source.

A producer must leave unknown fields unknown. It may not fill them from collection metadata, defaults, another source, or game assumptions unless that fact is explicitly part of its deterministic producer contract.

### Reconciliation algorithm

For each puzzle:

1. canonicalize every supplied semantic field before comparison;
2. group evidence values by semantic field/path;
3. ignore evidence that does not claim that field;
4. if all claims for the field are canonically equal, retain the value and all supporting provenance;
5. if claims disagree, raise a typed `PuzzleDefinitionConflictError` that names the puzzle, semantic field/path, and conflicting evidence references;
6. after reconciliation, validate cross-field invariants such as output scale/count and production/nullability;
7. if any required field remains unknown, return an explicitly unresolved coverage result and do not synthesize a `PuzzleDefinition`;
8. only complete reconciled semantic content is assigned a `puzzle_definition_id` and emitted as a canonical definition.

Input iteration order and source priority never decide a conflict. There is no preferred-source-wins rule in v1.

## Provenance and Observation consolidation

The existing repository already has canonical observation-shaped facts, but observation identity is currently implemented in more than one materialization module. Issue #61 needs semantic definitions to point to source observations without creating another provenance type.

Extract the existing `Observation` record shape plus canonical observation-ID helper into one shared narrow module. Migrate current solution observation production and release observation validation to consume that helper without changing valid existing IDs.

Semantic evidence from molecule-db is represented as puzzle metadata observations with `artifact_id = null`. Evidence decoded from an exact puzzle artifact links to the existing puzzle artifact observation/provenance and records the supporting `puzzle_artifact_id` on the definition.

The canonical definition stores sorted unique `source_observation_ids` and `puzzle_artifact_ids` only as provenance links. The underlying observations/artifacts remain authoritative for source paths, revisions, timestamps, hashes, and rights.

## Deterministic `.puzzle` decoder

Add a repository-native strict parser/decoder for Opus Magnum format-3 `.puzzle` bytes. It parses problem structure only and does not duplicate omsim simulation logic.

The parser follows the already public format represented by the pinned omsim `parse.c` / `parse.h` contract:

- format version `3`;
- puzzle name and creator metadata are parsed for format validation but are not semantic identity;
- `parts_available` availability mask;
- input/reagent molecules;
- output/product molecules;
- `output_scale`;
- optional production information with shrink/isolation flags, cabinets, conduits, and vials.

The Python parser is stricter than the permissive C byte readers where required for corpus integrity. It fails closed on:

- truncated fixed-width values;
- malformed or unterminated variable-length strings;
- impossible or excessive counts before allocation/iteration;
- unknown atom values;
- unknown bond bits;
- unknown availability bits;
- malformed production records;
- invalid molecule bonds;
- unsupported format versions;
- unexpected trailing bytes after a complete format-3 record.

The decoder maps raw format values into `PuzzleDefinitionEvidence` using canonical semantic vocabularies. It never writes or reconstructs `.puzzle` bytes.

### Differential contract

Pinned-upstream tests use exact fixtures acquired from the repository's pinned omsim revision and cross-check the Python parser's decoded structure against the same fields exposed by the upstream parser/decoder contract.

The differential test covers at least:

- availability/capability decoding;
- reagent/product counts and topology;
- atom types and coordinates;
- bond types and endpoints;
- output scale and target count;
- production absence/presence and production fields where an upstream fixture exists.

Hermetic unit tests independently exercise malformed/truncated byte cases and canonicalization behavior. Upstream tests remain explicitly marked `upstream`.

## Source producers

### Exact PuzzleArtifact producer

For every exact `PuzzleArtifact`, read bytes only through the authoritative `ContentStore`, validate artifact identity as today, decode them, and emit semantic evidence linked to that artifact and its observations.

If multiple exact artifacts exist for one puzzle, they may all contribute semantic evidence. Byte difference is not itself a semantic ambiguity. They are compatible when their decoded canonical semantics agree and a conflict when they disagree.

The present global `_require_unambiguous_exact_artifacts()` behavior therefore cannot remain the semantic materialization gate. Exact-artifact multiplicity is represented in artifact coverage. Under the current v1 verifier-selection policy, `verifier_ready` is true only when exactly one valid exact artifact is available for the puzzle. If a future explicit artifact-selection primitive is introduced, that primitive may define a different verifier-ready rule without changing semantic identity.

### molecule-db producer

Refactor the existing `MoleculeDbPuzzleSemantics` output into the shared evidence boundary.

molecule-db contributes only facts actually present in its pinned Rust source, currently including puzzle/catalog association and reagent/product topology/multiplicity. It does not claim allowed capabilities, output scale, or production constraints when those fields are not present in that source.

Therefore molecule-db alone does not automatically make a puzzle semantically complete. It can independently corroborate topology and can participate in a complete definition when other independent semantic evidence supplies the remaining required fields.

Future semantic sources must emit the same evidence type instead of adding source-specific semantic stores or reconciliation paths.

## Coverage model

Replace the current overloaded puzzle coverage boolean with three independently derived axes per puzzle:

- `semantic_covered`: a complete reconciled `PuzzleDefinition` exists;
- `artifact_covered`: at least one exact `PuzzleArtifact` exists;
- `verifier_ready`: the current verifier artifact-selection policy has exactly one valid exact artifact to select.

Coverage rows also expose the resolved `puzzle_definition_id` when present, exact artifact IDs, exact source IDs, and semantic source IDs. All counts and summaries are generated from materialization results.

`require_complete_puzzle_coverage()` used by WP-12 continues to gate on `verifier_ready`, not `semantic_covered`. Issue #61 must not weaken the 166-puzzle exact-artifact requirement for the v1 verification run.

A separate semantic-completeness gate is used by research/release consumers that require semantic definitions.

## Research/model serialization

The model/research puzzle serializer consumes `PuzzleDefinition`, not `.puzzle` bytes and not an artifact-bound normalized-puzzle record.

Retire misleading puzzle-side normalized-puzzle terminology. The existing serializer surface should be split or renamed so normalized solutions remain normalized-solution projections while puzzle serialization explicitly accepts semantic puzzle definitions.

The canonical JSON baseline remains a deterministic projection. Future model-oriented text formats must derive from the same `PuzzleDefinition` object and version their serializer independently; they may not become maintained semantic authorities.

## Rights boundary

`PuzzleDefinition` has no artifact-level `rights_status`. Semantic availability must never be used to upgrade or infer the redistribution status of any exact artifact.

The release semantic puzzle row is treated as derived metadata/semantic structure, not as publication of the underlying `.puzzle` payload. Raw artifact bytes remain governed by the existing per-artifact rights and payload policy.

This architectural separation is not a general copyright conclusion. It only defines corpus responsibilities: artifact rights live on artifacts and source observations, while semantic definitions do not masquerade as exact official artifacts or grant permission to redistribute them.

## Release migration

The release migration changes the existing `puzzles` config in place after WP-12 PR #58's release implementation surface is no longer concurrently owned.

A release puzzle row becomes conceptual collection metadata plus the complete semantic definition and its provenance references. It no longer requires or contains:

- `canonical_puzzle_artifact_id`;
- `puzzle_sha256`;
- `puzzle_bytes`;
- artifact-level `rights_status`.

Artifact bytes, hashes, byte lengths, rights, and observations remain canonical artifact/provenance facts in the materialization pipeline and `ContentStore`. They remain available to verification and any explicit rights-governed artifact export. They are not smuggled back into the semantic puzzle row through nested artifact payload fields.

The authoritative release-config specification removes the puzzle payload field instead of keeping a nullable compatibility slot. `payload_policy` continues to govern release configs that actually contain raw artifact payloads.

Release materialization requires one complete semantic definition for every emitted puzzle row. It validates the definition identity and provenance links, then projects semantic content without reading puzzle bytes.

Solution release and verification rows continue to trace verification to exact `puzzle_artifact_id` values. Thus consumers can use semantic puzzle definitions without binary payloads while verifier evidence still identifies the exact bytes used.

## Stack and collision plan

Implement issue #61 as three PR capabilities.

### PR A: semantic definition contract and reconciliation

Base: current `main`.

Owns:

- `puzzle-definition.schema.json` replacing `normalized-puzzle.schema.json`;
- semantic identity/canonicalization helpers;
- `PuzzleDefinitionEvidence` and deterministic reconciler;
- shared Observation identity extraction/consolidation;
- molecule-db semantic evidence producer;
- focused contract/reconciliation tests;
- the durable semantic-model portions of `docs/dataset-spec.md`.

Does not touch release puzzle schema/materialization, WP-12 orchestration, verifier behavior, or `.puzzle` parsing.

### PR B: native puzzle decoder and artifact semantic evidence

Stacked on PR A.

Owns:

- strict format-3 `.puzzle` parser;
- raw-to-canonical semantic vocabulary mappings;
- exact `PuzzleArtifact` semantic evidence production through `ContentStore`;
- reconciliation of multiple artifact-derived definitions;
- hermetic malformed-input tests;
- pinned omsim differential tests.

Does not change release schemas or verification authority.

### PR C: release, coverage, and serialization migration

Depends on PR B and WP-12 PR #58's release implementation. If #58 is still open when PR B is ready, PR C waits rather than independently editing the same release files.

After both dependencies are landed, PR C branches from their landed `main` state. If repository timing instead requires a temporary literal stack, it is based on the branch containing both dependency changes and is restacked onto `main` as soon as #58 lands.

Owns:

- puzzle release schema migration;
- release materialization from `PuzzleDefinition`;
- authoritative release-config payload-field update;
- three-axis puzzle coverage reporting;
- puzzle research/model serializer migration;
- tiny release fixtures and release tests;
- README/export/spec wording that currently equates exact bytes with semantic knowledge.

No PR preserves a compatibility path for artifact-bound normalized puzzle records.

## Testing strategy

Use focused red/green development for every behavioral slice.

PR A proves:

- semantic definitions validate without a puzzle artifact link;
- semantic identity ignores evidence/artifact ordering and source ordering;
- canonical molecule/bond ordering is stable while multiplicity is preserved;
- equal multi-source evidence reconciles;
- conflicting evidence fails closed with source context;
- incomplete evidence remains unresolved;
- molecule-db never synthesizes fields it does not know;
- Observation identity consolidation preserves existing solution observation IDs.

PR B proves:

- known format-3 fixtures decode into expected semantic content;
- byte-distinct fixtures with identical decoded semantics produce the same definition identity;
- multiple agreeing exact artifacts are semantic-compatible while verifier readiness remains a separate selection result;
- malformed/truncated/unknown-bit inputs fail closed;
- decoder output is independent of local cache root;
- pinned upstream parser behavior agrees for the supported format fields.

PR C proves:

- release puzzle rows validate and materialize with no exact artifact payload fields;
- release puzzle rows can be built from complete independently sourced semantics even when no exact artifact is present under subset/research policy;
- WP-12 complete verification still rejects missing or ambiguous verifier-ready exact artifacts;
- semantic/artifact/verifier-ready coverage are independently derived;
- verification rows still bind to exact `puzzle_artifact_id`;
- puzzle serialization consumes semantic definitions and does not read `ContentStore` bytes;
- repeated materialization is byte-identical at the canonical JSONL/manifest boundary;
- full repository validation remains green.

For the final release-affecting PR, run the complete validation sequence required by `AGENTS.md`, including the pinned upstream suite and tiny build/validate/stage workflow.

## Migration and deletion

This is a replacement, not an additive compatibility project.

Delete or replace obsolete concepts as their consumers migrate:

- `normalized-puzzle.schema.json`;
- `puzzle_artifact_id` as semantic-definition identity/required lineage;
- release puzzle binary/hash/rights fields;
- puzzle-side serializer terminology that implies the semantic definition is merely an artifact normalization;
- coverage logic that treats semantic evidence, artifact possession, and verifier readiness as one axis.

Do not retain adapters, aliases, duplicate schemas, or alternate readers solely to keep old internal call sites alive. Update repository-owned consumers in the same stack.

## Non-goals

Issue #61 does not:

- replace or reimplement libverify simulation;
- synthesize official `.puzzle` files from semantics;
- infer redistribution rights from semantic availability;
- loosen WP-12's exact-artifact verification gate;
- define semantic equivalence for solutions;
- create a database or semantic sidecar corpus;
- add hand-maintained semantic records for missing puzzles;
- add source-priority reconciliation rules;
- preserve the artifact-bound normalized-puzzle abstraction for compatibility.

## Completion criteria

Issue #61 is complete when the three-PR stack has landed and fresh validation proves:

1. a complete `PuzzleDefinition` can exist and validate without any exact artifact when independent evidence knows every required semantic field;
2. semantic identity is deterministic and independent of source/evidence ordering and binary identity;
3. exact artifacts and source observations remain traceable provenance without becoming semantic authority;
4. multiple byte-distinct artifacts with equal semantics converge on one definition;
5. semantic conflicts fail closed and unknown required fields are never silently filled;
6. the native decoder is covered by strict fixtures and the pinned upstream parser contract;
7. release and research consumers use full semantic definitions without reading puzzle bytes;
8. coverage reports semantic, artifact, and verifier-ready state separately;
9. verification remains bound to an explicit exact `PuzzleArtifact`;
10. durable documentation no longer equates possessing exact bytes with knowing the problem definition.
