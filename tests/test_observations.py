from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json


def _legacy_observation_id(body: dict[str, object]) -> str:
    payload = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return f"om.observation.sha256.{hashlib.sha256(payload).hexdigest()}"


def test_shared_observation_identity_preserves_existing_encoding() -> None:
    assert importlib.util.find_spec("opus_corpus.observations") is not None
    module = importlib.import_module("opus_corpus.observations")

    body = {
        "artifact_kind": "solution",
        "artifact_id": "om.solution.sha256." + "1" * 64,
        "puzzle_id": "om.puzzle.0001",
        "source_role": "artifact",
        "source_id": "om-archive",
        "source_revision": "rev",
        "source_object_id": None,
        "source_path": "puzzle/example.solution",
        "associated_artifact_path": None,
        "source_declared_puzzle_id": None,
        "source_url": None,
        "author": "Example",
        "retrieved_at": "2026-08-24T00:00:00Z",
        "claimed_cost": None,
        "claimed_cycles": None,
        "claimed_area": None,
        "claimed_instructions": None,
        "observed_sha256": "1" * 64,
        "source_evidence_sha256": "1" * 64,
        "source_evidence_byte_length": 42,
        "rights_status": "unknown",
        "importer_version": "solution-materializer-v1",
    }

    expected = _legacy_observation_id(body)
    assert module.observation_id(body) == expected
    assert module.observation_id(dict(reversed(tuple(body.items())))) == expected
