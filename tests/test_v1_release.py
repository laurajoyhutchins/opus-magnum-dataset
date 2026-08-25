from __future__ import annotations

import struct
from dataclasses import replace
from pathlib import Path

import pytest

from opus_corpus.adapters.omsim import OmsimAdapter
from opus_corpus.cache import ContentAddressedCache
from opus_corpus.collections import CollectionDefinition
from opus_corpus.config import CorpusConfig, load_config
from opus_corpus.libverify import OMSIM_LIBVERIFY_PROFILE
from opus_corpus.puzzle_materialization import PuzzleCoverageError
from opus_corpus.solution_normalizer import SolutionNormalizationError
from opus_corpus.v1_release import (
    V1ReleaseError,
    V1ReleaseReproducibilityError,
    build_v1_release,
)
from opus_corpus.verification import (
    VerificationInput,
    VerificationResult,
    verification_id,
)


class _FixtureVerifier:
    def verify(self, value: VerificationInput) -> VerificationResult:
        identity = {
            "puzzle_artifact_id": value.puzzle_artifact_id,
            "solution_id": value.solution_id,
            "verifier_implementation": "fixture-verifier",
            "verifier_revision": "fixture-verifier-rev",
            "verifier_sha256": "c" * 64,
            "validation_profile": value.validation_profile,
        }
        if value.solution_bytes == b"not-a-solution":
            return VerificationResult(
                verification_id=verification_id(**identity),
                **identity,
                parse_status="failed",
                simulation_status="not_run",
                cost=None,
                cycles=None,
                area=None,
                instructions=None,
                vanilla_constructible=None,
                record_eligible=None,
                error_code="solution_parse_failed",
                error_detail="fixture parse failure",
            )
        return VerificationResult(
            verification_id=verification_id(**identity),
            **identity,
            parse_status="passed",
            simulation_status="passed",
            cost=20,
            cycles=40,
            area=10,
            instructions=6,
            vanilla_constructible=None,
            record_eligible=None,
            error_code=None,
            error_detail=None,
        )


class _DriftingVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, value: VerificationInput) -> VerificationResult:
        self.calls += 1
        identity = {
            "puzzle_artifact_id": value.puzzle_artifact_id,
            "solution_id": value.solution_id,
            "verifier_implementation": "fixture-verifier",
            "verifier_revision": "fixture-verifier-rev",
            "verifier_sha256": "c" * 64,
            "validation_profile": value.validation_profile,
        }
        return VerificationResult(
            verification_id=verification_id(**identity),
            **identity,
            parse_status="passed",
            simulation_status="passed",
            cost=20 + self.calls,
            cycles=40,
            area=10,
            instructions=6,
            vanilla_constructible=None,
            record_eligible=None,
            error_code=None,
            error_detail=None,
        )


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="base-game-2026-06-16",
        inventory_sha256="a" * 64,
        puzzle_count=1,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0001",
                "display_name": "Fixture Puzzle",
                "kind": "campaign",
                "group": "chapter-1",
                "game_puzzle_id": "P001",
                "leaderboard_key": "FIXTURE_PUZZLE",
                "puzzle_type": "standard",
            },
        ),
        manifest={},
    )


def _valid_solution_bytes() -> bytes:
    return (
        struct.pack("<I", 7)
        + b"\x04P001"
        + b"\x07fixture"
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
    )


def _normalization_failure_solution_bytes() -> bytes:
    return (
        struct.pack("<I", 7)
        + b"\x04P001"
        + b"\x07fixture"
        + struct.pack("<I", 0)
        + struct.pack("<I", 1)
        + b"\x04arm1"
        + b"\x01"
        + struct.pack("<i", 0)
        + struct.pack("<i", 0)
        + struct.pack("<I", 1)
        + struct.pack("<i", 0)
        + struct.pack("<I", 0)
        + struct.pack("<I", 1)
        + struct.pack("<i", -1)
        + b"G"
        + struct.pack("<I", 0)
    )


def _valid_puzzle_bytes() -> bytes:
    reagent = struct.pack("<I", 1) + b"\x01\x00\x00" + struct.pack("<I", 0)
    product = struct.pack("<I", 1) + b"\x02\x00\x00" + struct.pack("<I", 0)
    return (
        struct.pack("<I", 3)
        + b"\x07fixture"
        + struct.pack("<Q", 0)
        + struct.pack("<Q", 0)
        + struct.pack("<I", 1)
        + reagent
        + struct.pack("<I", 1)
        + product
        + struct.pack("<I", 1)
        + b"\x00"
    )


def _cache_puzzle(cache_root: Path) -> None:
    ContentAddressedCache(cache_root).put_bytes(
        "omsim",
        OmsimAdapter.pinned_revision,
        "test/puzzle/campaign/P001.puzzle",
        _valid_puzzle_bytes(),
        rights_status="local_fetch_only",
    )


def _cache_solution(cache_root: Path, name: str, payload: bytes) -> None:
    ContentAddressedCache(cache_root).put_bytes(
        "om-leaderboard",
        "0cfd371ef66cf94eac3f7a7a06bc9ab959495576",
        f"CHAPTER_1/FIXTURE_PUZZLE/{name}.solution",
        payload,
        rights_status="local_fetch_only",
    )


def _config(tmp_path: Path) -> CorpusConfig:
    base = load_config(Path(__file__).resolve().parents[1] / "corpus.toml")
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    return replace(base, root=root, output_root=root / ".release")


def _release_output(config: CorpusConfig) -> Path:
    return config.output_root / "base-game-2026-06-16"


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_v1_release_runs_full_offline_pipeline_and_rebuild_gate(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    cache_root = tmp_path / "cache"
    config = _config(tmp_path)
    output_dir = _release_output(config)
    _cache_puzzle(cache_root)
    _cache_solution(cache_root, "good", _valid_solution_bytes())
    _cache_solution(cache_root, "bad", b"not-a-solution")

    manifest = build_v1_release(
        _collection(tmp_path),
        cache_root=cache_root,
        output_dir=output_dir,
        config=config,
        verifier=_FixtureVerifier(),
    )

    coverage = manifest.release_metadata["coverage"]
    assert manifest.coverage_policy == "complete"
    assert manifest.payload_policy == "metadata-only"
    assert coverage["puzzle_count"] == 1
    assert coverage["candidate_solution_count"] == 2
    assert coverage["verified_solution_count"] == 1
    assert coverage["rejected_solution_count"] == 1
    assert coverage["by_puzzle"]["om.puzzle.0001"]["state"] == "verified"
    assert manifest.configs["solutions"].row_count == 2
    assert manifest.configs["normalized"].row_count == 1
    assert manifest.release_metadata["validation_profile"] == OMSIM_LIBVERIFY_PROFILE
    assert (output_dir / "release-manifest.json").is_file()


def test_v1_release_fails_closed_when_normalizer_rejects_verifier_parse_success(
    tmp_path: Path,
) -> None:
    pytest.importorskip("pyarrow")
    cache_root = tmp_path / "cache"
    config = _config(tmp_path)
    output_dir = _release_output(config)
    _cache_puzzle(cache_root)
    _cache_solution(cache_root, "normalizer-rejects", _normalization_failure_solution_bytes())
    _cache_solution(cache_root, "normalizes", _valid_solution_bytes())

    with pytest.raises(SolutionNormalizationError, match="negative instruction cycle"):
        build_v1_release(
            _collection(tmp_path),
            cache_root=cache_root,
            output_dir=output_dir,
            config=config,
            verifier=_FixtureVerifier(),
        )

    assert not output_dir.exists()


def test_v1_release_rejects_cache_output_overlap_before_mutation(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    config = _config(tmp_path)
    cache_root = config.output_root / "cache"
    output_dir = config.output_root
    _cache_puzzle(cache_root)
    _cache_solution(cache_root, "good", _valid_solution_bytes())
    before = _tree_bytes(cache_root)

    with pytest.raises(V1ReleaseError, match="overlap"):
        build_v1_release(
            _collection(tmp_path),
            cache_root=cache_root,
            output_dir=output_dir,
            config=config,
            verifier=_FixtureVerifier(),
        )

    assert _tree_bytes(cache_root) == before


def test_v1_release_rejects_output_outside_configured_release_root(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    cache_root = tmp_path / "cache"
    config = _config(tmp_path)
    sentinel = config.root / "authority.txt"
    sentinel.write_text("repository authority\n", encoding="utf-8")
    _cache_puzzle(cache_root)
    _cache_solution(cache_root, "good", _valid_solution_bytes())

    with pytest.raises(V1ReleaseError, match="configured release root"):
        build_v1_release(
            _collection(tmp_path),
            cache_root=cache_root,
            output_dir=config.root,
            config=config,
            verifier=_FixtureVerifier(),
        )

    assert sentinel.read_text(encoding="utf-8") == "repository authority\n"


def test_v1_release_fails_before_verification_when_exact_puzzle_coverage_is_missing(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache"
    config = _config(tmp_path)
    output_dir = _release_output(config)
    _cache_solution(cache_root, "good", _valid_solution_bytes())

    with pytest.raises(PuzzleCoverageError, match=r"om\.puzzle\.0001"):
        build_v1_release(
            _collection(tmp_path),
            cache_root=cache_root,
            output_dir=output_dir,
            config=config,
            verifier=_FixtureVerifier(),
        )

    assert not output_dir.exists()


def test_v1_release_rejects_full_pipeline_rebuild_drift_without_publishing(
    tmp_path: Path,
) -> None:
    pytest.importorskip("pyarrow")
    cache_root = tmp_path / "cache"
    config = _config(tmp_path)
    output_dir = _release_output(config)
    _cache_puzzle(cache_root)
    _cache_solution(cache_root, "good", _valid_solution_bytes())

    with pytest.raises(V1ReleaseReproducibilityError, match="rebuild"):
        build_v1_release(
            _collection(tmp_path),
            cache_root=cache_root,
            output_dir=output_dir,
            config=config,
            verifier=_DriftingVerifier(),
        )

    assert not output_dir.exists()
