from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .hashing import canonical_json_bytes, sha256_bytes


def observation_id(body: Mapping[str, Any]) -> str:
    """Return the canonical identity for an observation body."""

    digest = sha256_bytes(canonical_json_bytes(dict(body)))
    return f"om.observation.sha256.{digest}"
