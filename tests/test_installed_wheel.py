from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path


def test_collection_validation_from_installed_wheel_outside_checkout(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    dist_dir = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel_path = next(dist_dir.glob("*.whl"))
    site_dir = tmp_path / "site"
    with zipfile.ZipFile(wheel_path) as wheel:
        wheel.extractall(site_dir)

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    source_manifest = project_root / "collections/base-game-2026-06-16.toml"
    with source_manifest.open("rb") as handle:
        inventory_name = tomllib.load(handle)["inventory_file"]
    manifest_path = runtime_dir / source_manifest.name
    shutil.copy2(source_manifest, manifest_path)
    shutil.copy2(source_manifest.parent / inventory_name, runtime_dir / inventory_name)

    code = f"""
from pathlib import Path
import opus_corpus
from opus_corpus.collections import validate_collection

site_dir = Path({str(site_dir)!r}).resolve()
package_file = Path(opus_corpus.__file__).resolve()
assert package_file.is_relative_to(site_dir), package_file
collection = validate_collection(Path({str(manifest_path)!r}))
assert collection.collection_id == "base-game-2026-06-16"
assert collection.puzzle_count == 166
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site_dir)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=runtime_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
