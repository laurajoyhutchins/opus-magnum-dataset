from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.molecule_db import MoleculeDbAdapter, MoleculeDbMolecule, MoleculeDbPuzzleSemantics
from .cache import CacheReceipt, ContentAddressedCache
from .collections import CollectionDefinition
from .content_store import ContentStore
from .errors import CorpusError
from .observations import observation_id
from .puzzle_definition import PuzzleDefinitionEvidence

_PUZZLE_MODEL_PATH = "src/puzzle.rs"
_MOLECULE_MODEL_PATH = "src/molecules.rs"
_REQUIRED_PATHS = (_MOLECULE_MODEL_PATH, _PUZZLE_MODEL_PATH)
_IMPORTER_VERSION = "molecule-db-semantic-v1"
_TRIPLEX_RE = re.compile(
    r"^Triplex \{ red: (?P<red>true|false), black: (?P<black>true|false), "
    r"yellow: (?P<yellow>true|false) \}$"
)


class MoleculeDbEvidenceError(CorpusError):
    """Raised when molecule-db semantics cannot be mapped canonically."""


@dataclass(frozen=True, slots=True)
class MoleculeDbSemanticEvidenceResult:
    evidence: tuple[PuzzleDefinitionEvidence, ...]
    observations: tuple[dict[str, Any], ...]


def _bond_types(value: str) -> list[str]:
    if value == "Normal":
        return ["normal"]
    match = _TRIPLEX_RE.fullmatch(value)
    if match is None:
        raise MoleculeDbEvidenceError(f"unsupported molecule-db bond type {value!r}")
    result: list[str] = []
    for source_name, semantic_name in (
        ("red", "triplex-red"),
        ("black", "triplex-black"),
        ("yellow", "triplex-yellow"),
    ):
        if match.group(source_name) == "true":
            result.append(semantic_name)
    if not result:
        raise MoleculeDbEvidenceError("molecule-db triplex bond type has no active component")
    return result


def _molecule(value: MoleculeDbMolecule) -> dict[str, Any]:
    return {
        "atoms": [
            {"atom_type": atom.atom_type.lower(), "q": atom.q, "r": atom.r}
            for atom in value.atoms
        ],
        "bonds": [
            {
                "a_q": bond.start_q,
                "a_r": bond.start_r,
                "b_q": bond.end_q,
                "b_r": bond.end_r,
                "bond_types": _bond_types(bond.bond_type),
            }
            for bond in value.bonds
        ],
    }


def molecule_db_semantic_claims(value: MoleculeDbPuzzleSemantics) -> dict[str, Any]:
    """Translate only semantic topology facts explicitly present in molecule-db."""

    reagents: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    for use in value.molecule_uses:
        reagents.extend(_molecule(use.molecule) for _ in range(use.reagent_count))
        products.extend(_molecule(use.molecule) for _ in range(use.product_count))

    if not reagents:
        raise MoleculeDbEvidenceError(
            f"{value.puzzle_id}: molecule-db supplies no reagent topology"
        )
    if not products:
        raise MoleculeDbEvidenceError(
            f"{value.puzzle_id}: molecule-db supplies no product topology"
        )
    return {"reagents": reagents, "products": products}


def _metadata_observation(
    receipt: CacheReceipt,
    semantics: MoleculeDbPuzzleSemantics,
) -> dict[str, Any]:
    body = {
        "artifact_kind": "puzzle",
        "artifact_id": None,
        "puzzle_id": semantics.puzzle_id,
        "source_role": "metadata",
        "source_id": receipt.source_id,
        "source_revision": receipt.revision,
        "source_object_id": semantics.game_puzzle_id,
        "source_path": receipt.upstream_path,
        "associated_artifact_path": None,
        "source_declared_puzzle_id": semantics.game_puzzle_id,
        "source_url": None,
        "author": None,
        "retrieved_at": receipt.retrieved_at,
        "claimed_cost": None,
        "claimed_cycles": None,
        "claimed_area": None,
        "claimed_instructions": None,
        "observed_sha256": None,
        "source_evidence_sha256": receipt.sha256,
        "source_evidence_byte_length": receipt.byte_length,
        "rights_status": receipt.rights_status,
        "importer_version": _IMPORTER_VERSION,
    }
    return {"observation_id": observation_id(body), **body}


def _read_required_sources(
    cache_root: Path,
) -> tuple[dict[str, CacheReceipt], dict[str, bytes]]:
    adapter = MoleculeDbAdapter()
    cache = ContentAddressedCache(cache_root)
    receipts = tuple(cache.iter_receipts(adapter.source_id, adapter.pinned_revision))
    by_path = {receipt.upstream_path: receipt for receipt in receipts}
    if len(by_path) != len(receipts) or set(by_path) != set(_REQUIRED_PATHS):
        raise MoleculeDbEvidenceError(
            f"incomplete or ambiguous molecule-db evidence at {adapter.pinned_revision}"
        )

    store = ContentStore(cache_root)
    payloads: dict[str, bytes] = {}
    for path in _REQUIRED_PATHS:
        receipt = by_path[path]
        store.require(receipt.sha256, receipt.byte_length)
        try:
            payloads[path] = store.object_path(receipt.sha256).read_bytes()
        except OSError as exc:
            raise MoleculeDbEvidenceError(
                f"cannot read cached molecule-db semantic source {path}"
            ) from exc
    return by_path, payloads


def materialize_molecule_db_semantic_evidence(
    collection: CollectionDefinition,
    cache_root: Path,
) -> MoleculeDbSemanticEvidenceResult:
    """Derive puzzle topology evidence from the two pinned molecule-db source facts."""

    by_path, payloads = _read_required_sources(Path(cache_root))
    adapter = MoleculeDbAdapter()
    semantics = adapter.parse_collection_semantics(
        collection,
        puzzle_source=payloads[_PUZZLE_MODEL_PATH],
        molecules_source=payloads[_MOLECULE_MODEL_PATH],
    )

    evidence: list[PuzzleDefinitionEvidence] = []
    observations: list[dict[str, Any]] = []
    for puzzle in semantics:
        claims = molecule_db_semantic_claims(puzzle)
        puzzle_observations = [
            _metadata_observation(by_path[path], puzzle) for path in _REQUIRED_PATHS
        ]
        observations.extend(puzzle_observations)
        evidence.append(
            PuzzleDefinitionEvidence(
                puzzle_id=puzzle.puzzle_id,
                observation_ids=tuple(
                    sorted(row["observation_id"] for row in puzzle_observations)
                ),
                claims=claims,
            )
        )

    observations.sort(key=lambda row: (row["puzzle_id"], row["source_path"]))
    evidence.sort(key=lambda row: (row.puzzle_id, row.observation_ids))
    return MoleculeDbSemanticEvidenceResult(
        evidence=tuple(evidence),
        observations=tuple(observations),
    )
