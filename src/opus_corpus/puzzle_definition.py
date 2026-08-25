from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import CorpusError
from .hashing import canonical_json_bytes, sha256_bytes
from .schema_resources import load_schema_resource

SCHEMA_VERSION = "puzzle-definition-v1"
_SEMANTIC_FIELDS = (
    "allowed_parts",
    "allowed_instructions",
    "reagents",
    "products",
    "output_scale",
    "target_output_count",
    "production",
    "production_constraints",
)


class PuzzleDefinitionError(CorpusError):
    """Raised when semantic puzzle content is invalid or incomplete."""


class PuzzleDefinitionConflictError(PuzzleDefinitionError):
    """Raised when immutable semantic evidence disagrees."""


@dataclass(frozen=True, slots=True)
class PuzzleDefinitionEvidence:
    puzzle_id: str
    observation_ids: tuple[str, ...]
    claims: Mapping[str, Any]
    puzzle_artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class PuzzleDefinitionResolution:
    definition: dict[str, Any] | None
    missing_fields: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    puzzle_artifact_ids: tuple[str, ...]


def _mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PuzzleDefinitionError(f"{label} must be an object")
    return dict(value)


def _sequence(value: object, *, label: str) -> list[Any]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise PuzzleDefinitionError(f"{label} must be an array")
    return list(value)


def _exact_keys(value: Mapping[str, Any], required: set[str], *, label: str) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        raise PuzzleDefinitionError(f"{label} is missing fields: {', '.join(missing)}")
    if extra:
        raise PuzzleDefinitionError(f"{label} has unknown fields: {', '.join(extra)}")


def _integer(value: object, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PuzzleDefinitionError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise PuzzleDefinitionError(f"{label} must be >= {minimum}")
    return value


def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PuzzleDefinitionError(f"{label} must be a non-empty string")
    return value


def _canonical_string_set(value: object, *, label: str) -> list[str]:
    items = [_string(item, label=f"{label} item") for item in _sequence(value, label=label)]
    return sorted(set(items))


def _canonical_atom(value: object) -> dict[str, Any]:
    row = _mapping(value, label="atom")
    _exact_keys(row, {"atom_type", "q", "r"}, label="atom")
    return {
        "atom_type": _string(row["atom_type"], label="atom_type"),
        "q": _integer(row["q"], label="atom q"),
        "r": _integer(row["r"], label="atom r"),
    }


def _canonical_bond(value: object) -> dict[str, Any]:
    row = _mapping(value, label="bond")
    _exact_keys(row, {"a_q", "a_r", "b_q", "b_r", "bond_types"}, label="bond")
    first = (
        _integer(row["a_q"], label="bond a_q"),
        _integer(row["a_r"], label="bond a_r"),
    )
    second = (
        _integer(row["b_q"], label="bond b_q"),
        _integer(row["b_r"], label="bond b_r"),
    )
    if second < first:
        first, second = second, first
    bond_types = _canonical_string_set(row["bond_types"], label="bond_types")
    if not bond_types:
        raise PuzzleDefinitionError("bond_types must not be empty")
    return {
        "a_q": first[0],
        "a_r": first[1],
        "b_q": second[0],
        "b_r": second[1],
        "bond_types": bond_types,
    }


def _canonical_molecule(value: object) -> dict[str, Any]:
    row = _mapping(value, label="molecule")
    _exact_keys(row, {"atoms", "bonds"}, label="molecule")
    atoms = [_canonical_atom(atom) for atom in _sequence(row["atoms"], label="atoms")]
    if not atoms:
        raise PuzzleDefinitionError("molecule atoms must not be empty")
    atoms.sort(key=canonical_json_bytes)
    positions = {(atom["q"], atom["r"]) for atom in atoms}
    bonds = [_canonical_bond(bond) for bond in _sequence(row["bonds"], label="bonds")]
    for bond in bonds:
        first = (bond["a_q"], bond["a_r"])
        second = (bond["b_q"], bond["b_r"])
        if first not in positions or second not in positions:
            raise PuzzleDefinitionError("bond endpoint does not reference an atom coordinate")
    bonds.sort(key=canonical_json_bytes)
    return {"atoms": atoms, "bonds": bonds}


def _canonical_molecules(value: object, *, label: str) -> list[dict[str, Any]]:
    molecules = [_canonical_molecule(item) for item in _sequence(value, label=label)]
    if not molecules:
        raise PuzzleDefinitionError(f"{label} must not be empty")
    molecules.sort(key=canonical_json_bytes)
    return molecules


def _canonical_coordinate(value: object, *, label: str) -> dict[str, int]:
    row = _mapping(value, label=label)
    _exact_keys(row, {"q", "r"}, label=label)
    return {
        "q": _integer(row["q"], label=f"{label} q"),
        "r": _integer(row["r"], label=f"{label} r"),
    }


def _canonical_production_constraints(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    row = _mapping(value, label="production_constraints")
    required = {
        "shrink_left",
        "shrink_right",
        "isolate_inputs_from_outputs",
        "cabinets",
        "conduits",
        "vials",
    }
    _exact_keys(row, required, label="production_constraints")
    for flag in ("shrink_left", "shrink_right", "isolate_inputs_from_outputs"):
        if not isinstance(row[flag], bool):
            raise PuzzleDefinitionError(f"production_constraints {flag} must be boolean")

    cabinets: list[dict[str, Any]] = []
    for value in _sequence(row["cabinets"], label="cabinets"):
        cabinet = _mapping(value, label="cabinet")
        _exact_keys(cabinet, {"q", "r", "cabinet_type"}, label="cabinet")
        cabinets.append(
            {
                "q": _integer(cabinet["q"], label="cabinet q"),
                "r": _integer(cabinet["r"], label="cabinet r"),
                "cabinet_type": _string(cabinet["cabinet_type"], label="cabinet_type"),
            }
        )
    cabinets.sort(key=canonical_json_bytes)

    conduits: list[dict[str, Any]] = []
    for value in _sequence(row["conduits"], label="conduits"):
        conduit = _mapping(value, label="conduit")
        _exact_keys(conduit, {"a_q", "a_r", "b_q", "b_r", "hexes"}, label="conduit")
        hexes = [
            _canonical_coordinate(item, label="conduit hex")
            for item in _sequence(conduit["hexes"], label="conduit hexes")
        ]
        hexes.sort(key=canonical_json_bytes)
        conduits.append(
            {
                "a_q": _integer(conduit["a_q"], label="conduit a_q"),
                "a_r": _integer(conduit["a_r"], label="conduit a_r"),
                "b_q": _integer(conduit["b_q"], label="conduit b_q"),
                "b_r": _integer(conduit["b_r"], label="conduit b_r"),
                "hexes": hexes,
            }
        )
    conduits.sort(key=canonical_json_bytes)

    vials: list[dict[str, Any]] = []
    for value in _sequence(row["vials"], label="vials"):
        vial = _mapping(value, label="vial")
        _exact_keys(vial, {"q", "r", "style", "count"}, label="vial")
        vials.append(
            {
                "q": _integer(vial["q"], label="vial q"),
                "r": _integer(vial["r"], label="vial r"),
                "style": _integer(vial["style"], label="vial style", minimum=0),
                "count": _integer(vial["count"], label="vial count", minimum=0),
            }
        )
    vials.sort(key=canonical_json_bytes)

    return {
        "shrink_left": row["shrink_left"],
        "shrink_right": row["shrink_right"],
        "isolate_inputs_from_outputs": row["isolate_inputs_from_outputs"],
        "cabinets": cabinets,
        "conduits": conduits,
        "vials": vials,
    }


def _canonical_field(name: str, value: object) -> Any:
    if name in {"allowed_parts", "allowed_instructions"}:
        return _canonical_string_set(value, label=name)
    if name in {"reagents", "products"}:
        return _canonical_molecules(value, label=name)
    if name == "output_scale":
        return _integer(value, label=name, minimum=1)
    if name == "target_output_count":
        return _integer(value, label=name, minimum=1)
    if name == "production":
        if not isinstance(value, bool):
            raise PuzzleDefinitionError("production must be boolean")
        return value
    if name == "production_constraints":
        return _canonical_production_constraints(value)
    raise PuzzleDefinitionError(f"unknown semantic field {name!r}")


def _canonical_semantics(semantics: Mapping[str, Any]) -> dict[str, Any]:
    values = dict(semantics)
    extra = sorted(set(values) - set(_SEMANTIC_FIELDS))
    if extra:
        raise PuzzleDefinitionError(f"unknown semantic fields: {', '.join(extra)}")
    missing = [name for name in _SEMANTIC_FIELDS if name not in values]
    if missing:
        raise PuzzleDefinitionError(f"missing semantic fields: {', '.join(missing)}")
    canonical = {name: _canonical_field(name, values[name]) for name in _SEMANTIC_FIELDS}
    _validate_cross_field_invariants(canonical)
    return canonical


def _validate_cross_field_invariants(semantics: Mapping[str, Any]) -> None:
    if semantics["target_output_count"] != 6 * semantics["output_scale"]:
        raise PuzzleDefinitionError("target_output_count must equal 6 * output_scale")
    if semantics["production"] and semantics["production_constraints"] is None:
        raise PuzzleDefinitionError("production puzzles require production_constraints")
    if not semantics["production"] and semantics["production_constraints"] is not None:
        raise PuzzleDefinitionError("non-production puzzles require null production_constraints")


def puzzle_definition_id(record: Mapping[str, Any]) -> str:
    puzzle_id = _string(record.get("puzzle_id"), label="puzzle_id")
    version = record.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise PuzzleDefinitionError(f"unsupported puzzle definition schema version {version!r}")
    missing = [name for name in _SEMANTIC_FIELDS if name not in record]
    if missing:
        raise PuzzleDefinitionError(f"missing semantic fields: {', '.join(missing)}")
    semantics = _canonical_semantics({name: record[name] for name in _SEMANTIC_FIELDS})
    identity_body = {
        "schema_version": SCHEMA_VERSION,
        "puzzle_id": puzzle_id,
        **semantics,
    }
    digest = sha256_bytes(canonical_json_bytes(identity_body))
    return f"om.puzzle-definition.sha256.{digest}"


def build_puzzle_definition(
    *,
    puzzle_id: str,
    semantics: Mapping[str, Any],
    source_observation_ids: Iterable[str] = (),
    puzzle_artifact_ids: Iterable[str] = (),
) -> dict[str, Any]:
    puzzle_id = _string(puzzle_id, label="puzzle_id")
    canonical = _canonical_semantics(semantics)
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "puzzle_id": puzzle_id,
        **canonical,
        "source_observation_ids": sorted(
            {_string(value, label="source observation id") for value in source_observation_ids}
        ),
        "puzzle_artifact_ids": sorted(
            {_string(value, label="puzzle artifact id") for value in puzzle_artifact_ids}
        ),
    }
    record["puzzle_definition_id"] = puzzle_definition_id(record)
    validate_puzzle_definition(record)
    return record


def validate_puzzle_definition(record: Mapping[str, Any]) -> None:
    schema = load_schema_resource("puzzle-definition.schema.json").schema
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(dict(record)),
        key=lambda error: (list(error.path), error.message),
    )
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise PuzzleDefinitionError(f"PuzzleDefinition violates the canonical schema: {detail}")
    expected = puzzle_definition_id(record)
    if record.get("puzzle_definition_id") != expected:
        raise PuzzleDefinitionError("puzzle definition identity does not match semantic content")


def _first_difference(left: object, right: object, path: str) -> str:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        keys = sorted(set(left) | set(right))
        for key in keys:
            if key not in left or key not in right:
                return f"{path}.{key}"
            if left[key] != right[key]:
                return _first_difference(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, list) and isinstance(right, list):
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            if left_item != right_item:
                return _first_difference(left_item, right_item, f"{path}[{index}]")
        if len(left) != len(right):
            return path
    return path


def _evidence_observation_ids(row: PuzzleDefinitionEvidence) -> tuple[str, ...]:
    observation_ids = tuple(
        sorted({_string(value, label="observation_id") for value in row.observation_ids})
    )
    if not observation_ids:
        raise PuzzleDefinitionError("semantic evidence requires at least one observation_id")
    return observation_ids


def _evidence_label(observation_ids: tuple[str, ...]) -> str:
    return ", ".join(observation_ids)


def reconcile_puzzle_definition(
    puzzle_id: str,
    evidence: Iterable[PuzzleDefinitionEvidence],
) -> PuzzleDefinitionResolution:
    puzzle_id = _string(puzzle_id, label="puzzle_id")
    rows = tuple(
        sorted(
            evidence,
            key=lambda row: (_evidence_observation_ids(row), row.puzzle_artifact_id or ""),
        )
    )
    observations: set[str] = set()
    artifacts: set[str] = set()
    claims_by_field: dict[str, list[tuple[tuple[str, ...], Any]]] = {
        name: [] for name in _SEMANTIC_FIELDS
    }

    for row in rows:
        if row.puzzle_id != puzzle_id:
            raise PuzzleDefinitionError(
                f"semantic evidence for {row.puzzle_id} cannot resolve {puzzle_id}"
            )
        observation_ids = _evidence_observation_ids(row)
        observations.update(observation_ids)
        if row.puzzle_artifact_id is not None:
            artifacts.add(_string(row.puzzle_artifact_id, label="puzzle_artifact_id"))
        extra = sorted(set(row.claims) - set(_SEMANTIC_FIELDS))
        if extra:
            raise PuzzleDefinitionError(
                f"{_evidence_label(observation_ids)}: unknown semantic claims: "
                f"{', '.join(extra)}"
            )
        for name, value in row.claims.items():
            claims_by_field[name].append((observation_ids, _canonical_field(name, value)))

    merged: dict[str, Any] = {}
    missing: list[str] = []
    for name in _SEMANTIC_FIELDS:
        claims = claims_by_field[name]
        if not claims:
            missing.append(name)
            continue
        first_observations, first_value = claims[0]
        for observation_ids, value in claims[1:]:
            if value != first_value:
                difference = _first_difference(first_value, value, name)
                raise PuzzleDefinitionConflictError(
                    f"{puzzle_id}: conflicting semantic evidence at {difference}: "
                    f"{_evidence_label(first_observations)}; "
                    f"{_evidence_label(observation_ids)}"
                )
        merged[name] = first_value

    source_observation_ids = tuple(sorted(observations))
    puzzle_artifact_ids = tuple(sorted(artifacts))
    if missing:
        return PuzzleDefinitionResolution(
            definition=None,
            missing_fields=tuple(sorted(missing)),
            source_observation_ids=source_observation_ids,
            puzzle_artifact_ids=puzzle_artifact_ids,
        )

    definition = build_puzzle_definition(
        puzzle_id=puzzle_id,
        semantics=merged,
        source_observation_ids=source_observation_ids,
        puzzle_artifact_ids=puzzle_artifact_ids,
    )
    return PuzzleDefinitionResolution(
        definition=definition,
        missing_fields=(),
        source_observation_ids=source_observation_ids,
        puzzle_artifact_ids=puzzle_artifact_ids,
    )
