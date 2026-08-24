from __future__ import annotations

from opus_corpus.card import render_dataset_card
from opus_corpus.release import ConfigRelease, ReleaseManifest


def manifest() -> ReleaseManifest:
    configs = {
        name: ConfigRelease(
            schema_path=f"schemas/{name}.schema.json",
            schema_sha256=name[0] * 64,
            records_sha256=name[-1] * 64,
            row_count=1,
            parquet_path=f"data/{name}/base_game_2026_06_16-00000-of-00001.parquet",
            parquet_sha256="d" * 64,
            source_path=f"fixtures/{name}.jsonl",
            source_sha256="e" * 64,
        )
        for name in ("puzzles", "solutions", "observations", "normalized")
    }
    return ReleaseManifest(
        format_version=1,
        corpus_schema_version="0.1",
        collection_id="base-game-2026-06-16",
        collection_inventory_sha256="a" * 64,
        split="base_game_2026_06_16",
        build_software_revision="deadbeef",
        build_config_sha256="b" * 64,
        payload_policy="metadata-only",
        coverage_policy="complete",
        release_metadata={
            "verifier_revision": "omsim-rev",
            "validation_profile": "v1",
            "normalizer_version": "n1",
            "source_classes": [{"source_id": "fixture", "revision": "r1"}],
            "coverage": {
                "puzzle_count": 1,
                "candidate_solution_count": 1,
                "verified_solution_count": 1,
                "rejected_solution_count": 0,
                "summary": "Fixture coverage.",
            },
            "known_limitations": ["Fixture only."],
        },
        release_metadata_sha256="c" * 64,
        configs=configs,
        logical_release_sha256="f" * 64,
    )


def test_card_maps_all_configs_to_immutable_split():
    card = render_dataset_card(
        manifest(), {"title": "Opus Magnum Corpus", "purpose": "Benchmarking."}
    )
    for name in ("puzzles", "solutions", "observations", "normalized"):
        assert f"config_name: {name}" in card
        assert f"path: data/{name}/base_game_2026_06_16-00000-of-00001.parquet" in card
    assert card.count("split: base_game_2026_06_16") == 4


def test_card_uses_release_metadata_not_checked_in_counts():
    card = render_dataset_card(
        manifest(), {"title": "Opus Magnum Corpus", "purpose": "Benchmarking."}
    )
    assert "Verified solutions: 1" in card
    assert "Verifier revision: `omsim-rev`" in card
    assert "Logical release hash: `" + "f" * 64 + "`" in card
    assert "Payload policy: `metadata-only`" in card
    assert "Coverage policy: `complete`" in card
