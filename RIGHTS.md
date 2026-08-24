# Rights and licensing

This file defines the scope of the repository license and the project's technical redistribution policy. It is not a legal determination about third-party content.

## Repository-authored material

The repository is licensed under the [MIT License](LICENSE).

Unless a file states otherwise, the MIT grant applies to the project's copyrightable contributions to repository-authored software, tests, schemas, documentation, collection/build machinery, and synthetic fixtures.

The MIT license does not grant rights the project does not own. In particular, committing metadata about an external work, recording provenance for it, or writing software that can acquire it does not relicense that external work.

## Third-party and upstream material

Third-party material remains subject to its own rights and license terms. The repository-level MIT license must not be interpreted as a blanket license for:

- official Opus Magnum puzzle or game-content bytes;
- player-authored or otherwise externally authored solution payloads;
- upstream source artifacts copied, cached, fetched, or represented by the corpus;
- third-party code or data that carries its own license or terms; or
- trademarks, names, artwork, or other rights belonging to their respective owners.

Source-specific evidence is recorded in [`docs/source-inventory.md`](docs/source-inventory.md) and focused acquisition documents. Those documents provide evidence for individual sources; this file defines the repository-wide policy boundary.

## Machine rights status

Raw artifact redistribution is governed by provenance-bearing `rights_status` facts, not by the repository license. The implemented statuses are:

- `redistributable`: available evidence permits this project to publish the raw payload subject to any applicable source-specific terms;
- `unknown`: the project does not have sufficient evidence to authorize raw-payload publication; and
- `local_fetch_only`: the raw payload may be acquired or used locally by the corpus pipeline but must not be republished by this project.

A rights status is not itself a copyright license. In particular, `redistributable` does not mean MIT-licensed. Any applicable source license or other terms remain distinct facts.

When multiple observations contribute to one exact-byte artifact, the corpus folds rights conservatively. A more permissive source observation must not silently broaden a more restrictive or unresolved rights state.

## Generated releases

Generated corpus releases are downstream projections and are not licensed wholesale under MIT merely because the build software is MIT-licensed.

The release payload policy remains fail-closed:

- `metadata-only` releases omit raw puzzle and solution bytes; and
- `include-permitted` releases may include raw bytes only when the artifact's `rights_status` is exactly `redistributable`.

Generated manifests and dataset cards must preserve the distinction between repository licensing and source-artifact rights. They must not infer a blanket dataset license from the repository's MIT license.

If a future release applies an additional license to a clearly separable body of project-owned metadata or other project-authored material, that grant must be explicit in the release metadata and must not broaden rights in third-party payloads.

## Fail closed

If rights evidence is absent, contradictory, or insufficient to justify redistribution, the project must omit the raw payload from publication rather than infer permission from availability, provenance, an upstream repository license, or the repository-level MIT license.
