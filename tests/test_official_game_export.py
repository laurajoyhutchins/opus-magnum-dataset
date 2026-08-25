from __future__ import annotations

from pathlib import Path

import pytest

from opus_corpus.adapters.official_game import (
    OfficialGameAcquisitionError,
    OfficialGameAdapter,
    prepare_official_source_root,
)
from opus_corpus.collections import CollectionDefinition


def _collection(tmp_path: Path) -> CollectionDefinition:
    return CollectionDefinition(
        collection_id="fixture",
        inventory_sha256="0" * 64,
        puzzle_count=2,
        manifest_path=tmp_path / "collection.toml",
        inventory_path=tmp_path / "collection.csv",
        inventory_rows=(
            {
                "puzzle_id": "om.puzzle.0001",
                "display_name": "Van Berlo's Wheel",
                "kind": "journal",
                "group": "journal-xcix-i",
                "game_puzzle_id": "P054",
                "leaderboard_key": "VAN_BERLO_S_WHEEL",
                "puzzle_type": "normal",
            },
            {
                "puzzle_id": "om.puzzle.0002",
                "display_name": "Lambent II/IX",
                "kind": "journal",
                "group": "journal-xcix-i",
                "game_puzzle_id": "P058",
                "leaderboard_key": "LAMBENT_II_IX",
                "puzzle_type": "normal",
            },
        ),
        manifest={},
    )


def _seven_bit_int(value: int) -> bytes:
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _puzzle_bytes(name: str, *, suffix: bytes = b"") -> bytes:
    encoded = name.encode("utf-8")
    return (
        (3).to_bytes(4, "little", signed=True)
        + _seven_bit_int(len(encoded))
        + encoded
        + suffix
    )


def test_prepare_official_source_root_reconciles_dump_by_embedded_name(tmp_path: Path):
    dump_root = tmp_path / "dump"
    output_root = tmp_path / "prepared"
    dump_root.mkdir()
    wheel = _puzzle_bytes("VAN BERLO'S WHEEL", suffix=b"\x01wheel")
    lambent = _puzzle_bytes("LAMBENT II/IX", suffix=b"\x02lambent")
    (dump_root / "z.puzzle").write_bytes(lambent)
    (dump_root / "a.puzzle").write_bytes(wheel)
    (dump_root / "tutorial.puzzle").write_bytes(_puzzle_bytes("TUTORIAL I"))

    manifest = prepare_official_source_root(
        _collection(tmp_path),
        dump_root,
        output_root,
        snapshot_id="steam-558991-4886674231773987379",
    )

    assert [(item.puzzle_id, item.relative_path.as_posix()) for item in manifest.mappings] == [
        ("om.puzzle.0001", "puzzles/P054.puzzle"),
        ("om.puzzle.0002", "puzzles/P058.puzzle"),
    ]
    assert (output_root / "puzzles/P054.puzzle").read_bytes() == wheel
    assert (output_root / "puzzles/P058.puzzle").read_bytes() == lambent
    assert (output_root / "official-puzzles.toml").read_text(encoding="utf-8") == (
        'schema_version = 1\n'
        'snapshot_id = "steam-558991-4886674231773987379"\n\n'
        '[[puzzles]]\n'
        'puzzle_id = "om.puzzle.0001"\n'
        'path = "puzzles/P054.puzzle"\n\n'
        '[[puzzles]]\n'
        'puzzle_id = "om.puzzle.0002"\n'
        'path = "puzzles/P058.puzzle"\n'
    )

    result = OfficialGameAdapter(output_root).fetch(_collection(tmp_path), tmp_path / "cache")
    assert result.candidate_count == 2
    assert result.puzzles_covered == 2


def test_prepare_official_source_root_is_independent_of_dump_paths(tmp_path: Path):
    collection = _collection(tmp_path)
    manifests: list[bytes] = []
    for side, filenames in (("left", ("b", "a")), ("right", ("x", "y"))):
        dump_root = tmp_path / side / "dump"
        output_root = tmp_path / side / "prepared"
        dump_root.mkdir(parents=True)
        (dump_root / f"{filenames[0]}.puzzle").write_bytes(_puzzle_bytes("LAMBENT II/IX"))
        (dump_root / f"{filenames[1]}.puzzle").write_bytes(_puzzle_bytes("VAN BERLO'S WHEEL"))
        prepare_official_source_root(collection, dump_root, output_root, snapshot_id="fixture")
        manifests.append((output_root / "official-puzzles.toml").read_bytes())

    assert manifests[0] == manifests[1]


def test_prepare_official_source_root_fails_closed_on_missing_coverage(tmp_path: Path):
    dump_root = tmp_path / "dump"
    output_root = tmp_path / "prepared"
    dump_root.mkdir()
    (dump_root / "only.puzzle").write_bytes(_puzzle_bytes("VAN BERLO'S WHEEL"))

    with pytest.raises(OfficialGameAcquisitionError, match="missing official puzzle coverage"):
        prepare_official_source_root(
            _collection(tmp_path), dump_root, output_root, snapshot_id="fixture"
        )

    assert not output_root.exists()


def test_prepare_official_source_root_fails_closed_on_ambiguous_name(tmp_path: Path):
    dump_root = tmp_path / "dump"
    output_root = tmp_path / "prepared"
    dump_root.mkdir()
    (dump_root / "one.puzzle").write_bytes(
        _puzzle_bytes("VAN BERLO'S WHEEL", suffix=b"first")
    )
    (dump_root / "two.puzzle").write_bytes(
        _puzzle_bytes("VAN BERLO'S WHEEL", suffix=b"second")
    )
    (dump_root / "lambent.puzzle").write_bytes(_puzzle_bytes("LAMBENT II/IX"))

    with pytest.raises(OfficialGameAcquisitionError, match="ambiguous official puzzle dump"):
        prepare_official_source_root(
            _collection(tmp_path), dump_root, output_root, snapshot_id="fixture"
        )

    assert not output_root.exists()


def test_prepare_official_source_root_rejects_existing_or_overlapping_destination(
    tmp_path: Path,
):
    dump_root = tmp_path / "dump"
    dump_root.mkdir()
    (dump_root / "wheel.puzzle").write_bytes(_puzzle_bytes("VAN BERLO'S WHEEL"))
    (dump_root / "lambent.puzzle").write_bytes(_puzzle_bytes("LAMBENT II/IX"))

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(OfficialGameAcquisitionError, match="destination already exists"):
        prepare_official_source_root(
            _collection(tmp_path), dump_root, existing, snapshot_id="fixture"
        )

    with pytest.raises(OfficialGameAcquisitionError, match="overlap"):
        prepare_official_source_root(
            _collection(tmp_path),
            dump_root,
            dump_root / "prepared",
            snapshot_id="fixture",
        )
