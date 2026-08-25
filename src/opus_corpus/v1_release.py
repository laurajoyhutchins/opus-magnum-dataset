from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .collections import CollectionDefinition
from .config import CorpusConfig
from .content_store import ContentStore
from .directory_publication import publish_directory
from .errors import CorpusError
from .hashing import canonical_json_bytes
from .libverify import OMSIM_LIBVERIFY_PROFILE
from .path_safety import resolve_disjoint_trees
from .puzzle_materialization import (
    materialize_puzzle_artifacts,
    require_complete_puzzle_coverage,
)
from .release import ReleaseManifest, build_release, validate_release
from .release_materialization import materialize_release_inputs
from .solution_materialization import materialize_solution_facts
from .solution_normalizer import OpusSolutionNormalizer, normalize_solution_artifacts
from .verification import Verifier
from .verification_materialization import materialize_verifications

V1_CORPUS_SCHEMA_VERSION = "0.1"


class V1ReleaseError(CorpusError):
    """Raised when the complete v1 release cannot be materialized safely."""


class V1ReleaseReproducibilityError(V1ReleaseError):
    """Raised when two full offline rebuilds do not reproduce the same manifest."""


def _write_release_metadata_template(
    destination: Path,
    collection: CollectionDefinition,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    template = {
        "release_kind": "complete-v1",
        "corpus_schema_version": V1_CORPUS_SCHEMA_VERSION,
        "coverage": {
            "summary": (
                "Complete verifier-backed release for " f"{collection.collection_id}."
            )
        },
        "known_limitations": [],
    }
    (destination / "release-metadata.json").write_bytes(
        canonical_json_bytes(template) + b"\n"
    )


def _resolve_v1_output(config: CorpusConfig, output_dir: Path) -> Path:
    repository_root = Path(config.root).resolve()
    release_root = Path(config.output_root).resolve()
    output = Path(output_dir).resolve()

    if release_root == repository_root or release_root in repository_root.parents:
        raise V1ReleaseError(
            "configured release root must not be the repository root or its ancestor: "
            f"{release_root}"
        )
    if output != release_root and release_root not in output.parents:
        raise V1ReleaseError(
            "v1 release output must be within the configured release root: "
            f"{release_root}; got {output}"
        )
    return output


def _build_once(
    collection: CollectionDefinition,
    *,
    cache_root: Path,
    workspace: Path,
    config: CorpusConfig,
    verifier: Verifier,
    payload_policy: str,
) -> tuple[ReleaseManifest, Path]:
    puzzles = materialize_puzzle_artifacts(collection, cache_root)
    require_complete_puzzle_coverage(puzzles)

    solutions = materialize_solution_facts(collection, cache_root)
    store = ContentStore(cache_root)
    verifications = materialize_verifications(
        (*puzzles.artifacts, *solutions.artifacts),
        store=store,
        verifier=verifier,
        validation_profile=OMSIM_LIBVERIFY_PROFILE,
    )
    parseable_solution_ids = {
        row.solution_id for row in verifications if row.parse_status == "passed"
    }
    parseable_solutions = tuple(
        row
        for row in solutions.artifacts
        if row.artifact_id in parseable_solution_ids
    )
    normalized = normalize_solution_artifacts(
        parseable_solutions,
        store,
        OpusSolutionNormalizer(),
    )

    input_dir = workspace / "inputs"
    release_dir = workspace / "release"
    _write_release_metadata_template(input_dir, collection)
    materialize_release_inputs(
        collection,
        input_dir,
        puzzle_artifacts=puzzles.artifacts,
        puzzle_provenance=puzzles.provenance,
        solution_artifacts=solutions.artifacts,
        observations=solutions.observations,
        verifications=verifications,
        normalized_solutions=normalized,
        payload_policy=payload_policy,
        store=store,
    )
    manifest = build_release(
        collection,
        input_dir,
        release_dir,
        config,
        payload_policy,
        coverage_policy="complete",
    )
    validate_release(collection, release_dir, config)
    return manifest, release_dir


def build_v1_release(
    collection: CollectionDefinition,
    *,
    cache_root: Path,
    output_dir: Path,
    config: CorpusConfig,
    verifier: Verifier,
    payload_policy: str = "metadata-only",
) -> ReleaseManifest:
    """Build and atomically publish a complete release after a full offline replay."""

    output_dir = _resolve_v1_output(config, output_dir)
    try:
        cache_root, output_dir = resolve_disjoint_trees(cache_root, output_dir)
    except ValueError as exc:
        raise V1ReleaseError(f"v1 release cache/output overlap: {exc}") from exc

    try:
        with tempfile.TemporaryDirectory(prefix="opus-corpus-v1-") as temp_root:
            root = Path(temp_root)
            first_manifest, first_release = _build_once(
                collection,
                cache_root=cache_root,
                workspace=root / "first",
                config=config,
                verifier=verifier,
                payload_policy=payload_policy,
            )
            _, second_release = _build_once(
                collection,
                cache_root=cache_root,
                workspace=root / "second",
                config=config,
                verifier=verifier,
                payload_policy=payload_policy,
            )

            first_manifest_bytes = (first_release / "release-manifest.json").read_bytes()
            second_manifest_bytes = (second_release / "release-manifest.json").read_bytes()
            if first_manifest_bytes != second_manifest_bytes:
                raise V1ReleaseReproducibilityError(
                    "full offline rebuild did not reproduce the canonical release manifest"
                )

            with publish_directory(output_dir) as candidate:
                shutil.copytree(first_release, candidate, dirs_exist_ok=True)
                validate_release(collection, candidate, config)
    except V1ReleaseReproducibilityError:
        raise
    except OSError as exc:
        raise V1ReleaseError(f"v1 release filesystem operation failed: {exc}") from exc

    return first_manifest
