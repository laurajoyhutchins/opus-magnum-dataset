from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import PayloadPolicyError, ValidationError

PAYLOAD_FIELDS = {"puzzles": "puzzle_bytes", "solutions": "solution_bytes"}
POLICIES = {"metadata-only", "include-permitted"}


def validate_payload_policy(
    config_name: str, rows: Sequence[Mapping[str, Any]], policy: str
) -> None:
    if policy not in POLICIES:
        raise PayloadPolicyError(
            [
                ValidationError(
                    "payload_policy_invalid",
                    f"unknown payload policy {policy!r}",
                    config_name,
                )
            ]
        )
    payload_field = PAYLOAD_FIELDS.get(config_name)
    if payload_field is None:
        return
    errors: list[ValidationError] = []
    for index, row in enumerate(rows, start=1):
        payload = row.get(payload_field)
        if payload in (None, "", b""):
            continue
        identity = row.get("puzzle_id") or row.get("solution_id") or f"row {index}"
        if policy == "metadata-only":
            errors.append(
                ValidationError(
                    "payload_forbidden",
                    f"{identity}: {payload_field} must be null under metadata-only",
                    config_name,
                    index,
                )
            )
        elif row.get("rights_status") != "redistributable":
            errors.append(
                ValidationError(
                    "payload_rights_violation",
                    f"{identity}: bytes require rights_status=redistributable",
                    config_name,
                    index,
                )
            )
    if errors:
        raise PayloadPolicyError(errors)
