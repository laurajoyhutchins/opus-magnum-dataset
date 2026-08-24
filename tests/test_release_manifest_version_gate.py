from __future__ import annotations

import json
from pathlib import Path

import pytest

from opus_corpus.errors import ReleaseValidationError
from opus_corpus.release import validate_release


@pytest.mark.parametrize("format_version", [1, 999])
def test_validate_release_rejects_unsupported_version_before_v2_decode(
    tmp_path: Path, format_version: int
):
    (tmp_path / "release-manifest.json").write_text(
        json.dumps({"format_version": format_version}),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseValidationError) as exc:
        validate_release(object(), tmp_path, object())

    assert {error.code for error in exc.value.errors} == {
        "release_manifest_format_unsupported"
    }
    assert str(format_version) in exc.value.errors[0].detail
