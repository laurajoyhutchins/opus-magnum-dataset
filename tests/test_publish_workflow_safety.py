"""Protect the secret-bearing manual publish workflow against shell source injection."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

PUBLISH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish.yml"


def _run_fragments(workflow: str) -> list[str]:
    """Return every YAML run scalar and literal block without a YAML dependency."""
    lines = workflow.splitlines()
    result: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)run:\s*(.*)$", line)
        if match is None:
            continue
        indent = len(match.group(1))
        fragment = match.group(2)
        if fragment == "|":
            parts = []
            for next_line in lines[index + 1 :]:
                if next_line.strip() and len(next_line) - len(next_line.lstrip()) <= indent:
                    break
                parts.append(next_line)
            fragment = "\n".join(parts)
        result.append(fragment)
    return result


def test_dispatch_values_are_never_embedded_into_shell_source() -> None:
    content = PUBLISH.read_text(encoding="utf-8")
    scripts = _run_fragments(content)
    assert scripts, "publish workflow must actually contain commands"
    for script in scripts:
        assert not re.search(r"\$\{\{\s*(?:inputs|github\.event\.inputs)\.", script)
    assert 'release build "$RELEASE_COLLECTION" --input "$RELEASE_INPUT_PATH"' in content
    assert 'release validate "$RELEASE_COLLECTION"' in content
    assert 'release publish "$RELEASE_COLLECTION"' in content


def test_dispatch_environment_bindings_and_least_privileged_job() -> None:
    content = PUBLISH.read_text(encoding="utf-8")
    for binding in (
        "RELEASE_COLLECTION: ${{ inputs.collection }}",
        "RELEASE_INPUT_PATH: ${{ inputs.input_path }}",
        "RELEASE_PAYLOAD_POLICY: ${{ inputs.payload_policy }}",
    ):
        assert binding in content
    assert "permissions:\n      contents: read" in content
    assert content.count("HF_TOKEN:") == 1
    assert content.index("HF_TOKEN:") > content.index("- name: Publish generated projection")


@pytest.mark.parametrize(
    "hostile",
    [
        "$(touch SHOULD_NOT_EXIST)",
        '"; touch SHOULD_NOT_EXIST; echo "',
        "\n>SHOULD_NOT_EXIST\n",
        "`touch SHOULD_NOT_EXIST`",
    ],
)
def test_quoted_env_value_is_data_not_shell_program(tmp_path: Path, hostile: str) -> None:
    # This matches the shell boundary actually used in the publish workflow.
    env = {**os.environ, "RELEASE_COLLECTION": hostile}
    result = subprocess.run(
        ["bash", "-c", 'printf "%s" "$RELEASE_COLLECTION"'],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == hostile
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()
