from __future__ import annotations

import pytest

from opus_corpus.serialization import ModelPuzzleTextSerializer


def test_model_puzzle_text_serializer_version_is_not_constructor_configurable() -> None:
    with pytest.raises(TypeError):
        ModelPuzzleTextSerializer(version="2")
