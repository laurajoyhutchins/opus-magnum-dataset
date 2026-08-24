from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .release import ReleaseManifest


def _text(value: Any, default: str = "not supplied") -> str:
    if value is None or value == "":
        return default
    return str(value)


def render_dataset_card(manifest: ReleaseManifest, card_settings: Mapping[str, Any]) -> str:
    lines = ["---", "configs:"]
    for name, entry in sorted(manifest.configs.items()):
        lines.extend(
            [
                f"- config_name: {name}",
                "  data_files:",
                f"  - split: {manifest.split}",
                f"    path: {entry.parquet_path}",
            ]
        )
    lines.extend(["---", ""])

    title = _text(card_settings.get("title"), "Opus Magnum Dataset")
    purpose = _text(
        card_settings.get("purpose"),
        "A reproducible, provenance-preserving corpus of Opus Magnum puzzles and solutions.",
    )
    metadata = manifest.release_metadata
    coverage = metadata.get("coverage", {}) if isinstance(metadata.get("coverage"), dict) else {}
    source_classes = metadata.get("source_classes", [])
    limitations = metadata.get("known_limitations", [])
    if not isinstance(source_classes, list):
        source_classes = []
    if not isinstance(limitations, list):
        limitations = []

    lines.extend(
        [
            f"# {title}",
            "",
            purpose,
            "",
            "## Release",
            "",
            f"- Corpus schema version: `{manifest.corpus_schema_version}`",
            f"- Collection: `{manifest.collection_id}`",
            f"- Split: `{manifest.split}`",
            f"- Logical release hash: `{manifest.logical_release_sha256}`",
            f"- Build software revision: `{_text(manifest.build_software_revision)}`",
            f"- Payload policy: `{manifest.payload_policy}`",
            f"- Coverage policy: `{manifest.coverage_policy}`",
            f"- Verifier revision: `{_text(metadata.get('verifier_revision'))}`",
            f"- Validation profile: `{_text(metadata.get('validation_profile'))}`",
            f"- Normalizer version: `{_text(metadata.get('normalizer_version'))}`",
            "",
            "## Coverage",
            "",
            f"- Puzzles: {coverage.get('puzzle_count', 0)}",
            f"- Candidate solutions: {coverage.get('candidate_solution_count', 0)}",
            f"- Verified solutions: {coverage.get('verified_solution_count', 0)}",
            f"- Rejected solutions: {coverage.get('rejected_solution_count', 0)}",
            "- Per-puzzle coverage: `release-manifest.json` → "
            "`release_metadata.coverage.by_puzzle`",
            f"- Summary: {_text(coverage.get('summary'))}",
            "",
            "## Sources",
            "",
        ]
    )
    if source_classes:
        for source in source_classes:
            if isinstance(source, dict):
                lines.append(
                    f"- `{_text(source.get('source_id'))}` at `{_text(source.get('revision'))}`"
                )
    else:
        lines.append("- No publishable source revision metadata supplied.")

    rights = _text(
        card_settings.get("rights_caveat"),
        "Raw bytes are included only when the release payload policy and per-artifact "
        "rights status permit redistribution.",
    )
    reproducibility = _text(
        card_settings.get("reproducibility_command"),
        f"uv run opus-corpus release validate {manifest.collection_id} --output <release-dir>",
    )
    lines.extend(
        [
            "",
            "## Rights and payload policy",
            "",
            rights,
            "",
            "## Reproducibility",
            "",
            f"`{reproducibility}`",
            "",
            "## Known limitations",
            "",
        ]
    )
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append("- No additional limitations supplied in release metadata.")
    lines.append("")
    return "\n".join(lines)
