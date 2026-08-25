from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.molecule_db import MoleculeDbAdapter
from .cache import ContentAddressedCache
from .collections import CollectionDefinition
from .content_store import ContentStore
from .errors import CorpusError
from .ingestion import ArtifactProvenance, ArtifactRecord
from .molecule_db_evidence import materialize_molecule_db_semantic_evidence
from .puzzle_definition import (
    PuzzleDefinitionEvidence,
    PuzzleDefinitionResolution,
    reconcile_puzzle_definition,
)
from .puzzle_materialization import (
    PuzzleCoverage,
    derive_puzzle_coverage,
    materialize_puzzle_artifact_semantic_evidence,
    materialize_puzzle_artifacts,
    materialize_puzzle_provenance_observations,
)


class PuzzleFactsError(CorpusError):
    """Raised when semantic puzzle facts cannot be reconciled with provenance."""


@dataclass(frozen=True, slots=True)
class PuzzleDefinitionMaterializationResult:
    definitions: tuple[dict[str, Any], ...]
    resolutions: tuple[PuzzleDefinitionResolution, ...]


@dataclass(frozen=True, slots=True)
class PuzzleFactsResult:
    artifacts: tuple[ArtifactRecord, ...]
    provenance: tuple[ArtifactProvenance, ...]
    definitions: tuple[dict[str, Any], ...]
    observations: tuple[dict[str, Any], ...]
    coverage: tuple[PuzzleCoverage, ...]


def materialize_puzzle_definitions(
    collection: CollectionDefinition,
    evidence: Iterable[PuzzleDefinitionEvidence],
) -> PuzzleDefinitionMaterializationResult:
    """Reconcile source evidence into at most one complete definition per collection puzzle."""

    collection_ids = tuple(row["puzzle_id"] for row in collection.inventory_rows)
    known_ids = set(collection_ids)
    by_puzzle: dict[str, list[PuzzleDefinitionEvidence]] = {}
    for row in evidence:
        if row.puzzle_id not in known_ids:
            raise PuzzleFactsError(
                f"semantic evidence references puzzle outside collection: {row.puzzle_id}"
            )
        by_puzzle.setdefault(row.puzzle_id, []).append(row)

    definitions: list[dict[str, Any]] = []
    resolutions: list[PuzzleDefinitionResolution] = []
    for puzzle_id in collection_ids:
        resolution = reconcile_puzzle_definition(puzzle_id, by_puzzle.get(puzzle_id, ()))
        resolutions.append(resolution)
        if resolution.definition is not None:
            definitions.append(resolution.definition)

    definitions.sort(key=lambda row: row["puzzle_id"])
    return PuzzleDefinitionMaterializationResult(
        definitions=tuple(definitions),
        resolutions=tuple(resolutions),
    )


def _semantic_sources(
    definitions: Iterable[Mapping[str, Any]],
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[str, ...]]:
    observation_by_id: dict[str, Mapping[str, Any]] = {}
    for row in observations:
        observation_id = row.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id:
            raise PuzzleFactsError("semantic observation has invalid observation_id")
        previous = observation_by_id.setdefault(observation_id, row)
        if previous != row:
            raise PuzzleFactsError(
                f"conflicting semantic observations share identity {observation_id}"
            )

    result: dict[str, tuple[str, ...]] = {}
    for definition in definitions:
        puzzle_id = definition["puzzle_id"]
        source_ids: set[str] = set()
        for observation_id in definition["source_observation_ids"]:
            observation = observation_by_id.get(observation_id)
            if observation is None:
                raise PuzzleFactsError(
                    f"{puzzle_id}: PuzzleDefinition references missing observation "
                    f"{observation_id}"
                )
            source_id = observation.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                raise PuzzleFactsError(
                    f"{observation_id}: semantic observation has invalid source_id"
                )
            source_ids.add(source_id)
        result[puzzle_id] = tuple(sorted(source_ids))
    return result


def materialize_cached_puzzle_facts(
    collection: CollectionDefinition,
    cache_root: Path,
) -> PuzzleFactsResult:
    """Materialize exact artifacts, semantic definitions, provenance, and coverage from cache."""

    cache_root = Path(cache_root)
    artifact_result = materialize_puzzle_artifacts(collection, cache_root)
    puzzle_observations = materialize_puzzle_provenance_observations(
        artifact_result.artifacts,
        artifact_result.provenance,
    )
    store = ContentStore(cache_root)
    evidence = list(
        materialize_puzzle_artifact_semantic_evidence(
            artifact_result.artifacts,
            puzzle_observations,
            store,
        )
    )
    semantic_observations = list(puzzle_observations)

    molecule_adapter = MoleculeDbAdapter()
    molecule_receipts = tuple(
        ContentAddressedCache(cache_root).iter_receipts(
            molecule_adapter.source_id,
            molecule_adapter.pinned_revision,
        )
    )
    if molecule_receipts:
        molecule_result = materialize_molecule_db_semantic_evidence(collection, cache_root)
        evidence.extend(molecule_result.evidence)
        semantic_observations.extend(molecule_result.observations)

    definition_result = materialize_puzzle_definitions(collection, evidence)
    unique_observations = {
        row["observation_id"]: row for row in semantic_observations
    }
    observations = tuple(unique_observations[key] for key in sorted(unique_observations))
    semantic_source_ids = _semantic_sources(definition_result.definitions, observations)
    coverage = derive_puzzle_coverage(
        collection,
        artifact_result.artifacts,
        artifact_result.provenance,
        definitions=definition_result.definitions,
        semantic_source_ids_by_puzzle=semantic_source_ids,
    )
    return PuzzleFactsResult(
        artifacts=artifact_result.artifacts,
        provenance=artifact_result.provenance,
        definitions=definition_result.definitions,
        observations=observations,
        coverage=coverage,
    )
