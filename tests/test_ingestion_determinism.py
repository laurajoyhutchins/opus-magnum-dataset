from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

_HASH_SEEDS = ("1", "2", "3", "4")

_INGESTION_SCRIPT = textwrap.dedent(
    """
    from dataclasses import asdict
    import json
    from pathlib import Path
    import tempfile

    from opus_corpus.cache import CacheReceipt
    from opus_corpus.content_store import ContentStore
    from opus_corpus.ingestion import ObservedArtifactCandidate, ingest_artifacts

    with tempfile.TemporaryDirectory() as root:
        store = ContentStore(Path(root))
        stored = store.put_bytes(b"deterministic solution")
        receipt = CacheReceipt(
            source_id="source",
            revision="revision-a",
            upstream_path="path/a.solution",
            sha256=stored.sha256,
            byte_length=stored.byte_length,
            rights_status="local_fetch_only",
            retrieved_at="2026-08-24T12:00:00+00:00",
        )
        common = dict(
            artifact_kind="solution",
            puzzle_id="om.puzzle.0001",
            artifact_format="solution",
            artifact_receipt=receipt,
            evidence_receipt=None,
            source_url=None,
            author=None,
            claimed_cost=None,
            claimed_cycles=None,
            claimed_area=None,
            claimed_instructions=None,
        )
        candidates = [
            ObservedArtifactCandidate(source_object_id=None, **common),
            ObservedArtifactCandidate(source_object_id="", **common),
        ]
        result = ingest_artifacts(candidates, store)
        print(json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
    """
)


def _run_ingestion(seed: str) -> str:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = seed
    completed = subprocess.run(
        [sys.executable, "-c", _INGESTION_SCRIPT],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return completed.stdout.strip()


def test_public_ingestion_result_is_stable_across_pythonhashseed_values() -> None:
    outputs = {seed: _run_ingestion(seed) for seed in _HASH_SEEDS}

    assert len(set(outputs.values())) == 1, outputs
    result = json.loads(next(iter(outputs.values())))
    assert [row["source_object_id"] for row in result["provenance"]] == [None, ""]
