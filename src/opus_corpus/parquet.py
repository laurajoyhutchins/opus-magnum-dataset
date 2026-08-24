from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from .config import CorpusConfig
from .hashing import canonical_json_bytes

PAYLOAD_FIELDS = {"puzzles": "puzzle_bytes", "solutions": "solution_bytes"}


def _to_arrow_rows(config_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload_field = PAYLOAD_FIELDS.get(config_name)
    converted: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if payload_field and isinstance(item.get(payload_field), str):
            item[payload_field] = base64.b64decode(item[payload_field], validate=True)
        if config_name == "normalized":
            item["parts"] = [
                {
                    **part,
                    "parameters": canonical_json_bytes(part["parameters"]).decode("utf-8"),
                }
                for part in item.get("parts", [])
            ]
        converted.append(item)
    return converted


def _from_arrow_rows(config_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload_field = PAYLOAD_FIELDS.get(config_name)
    converted: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if payload_field and isinstance(item.get(payload_field), bytes | bytearray):
            item[payload_field] = base64.b64encode(bytes(item[payload_field])).decode("ascii")
        if config_name == "normalized":
            item["parts"] = [
                {
                    **part,
                    "parameters": json.loads(part["parameters"]),
                }
                for part in item.get("parts", [])
            ]
        converted.append(item)
    return converted


def write_parquet(
    config_name: str, rows: list[dict[str, Any]], path: Path, config: CorpusConfig
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(_to_arrow_rows(config_name, rows))
    pq.write_table(
        table,
        path,
        compression=config.compression,
        use_dictionary=config.use_dictionary,
        write_statistics=config.write_statistics,
    )


def read_parquet(config_name: str, path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    rows = pq.read_table(path).to_pylist()
    return _from_arrow_rows(config_name, rows)
