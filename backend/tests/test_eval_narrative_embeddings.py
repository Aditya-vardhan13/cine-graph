import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("eval_narrative_embeddings", Path(__file__).resolve().parents[2] / "scripts/eval_narrative_embeddings.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_cosine_rejects_invalid_vectors_and_preserves_similarity():
    assert module.cosine([1, 0], [1, 0]) == 1
    assert module.cosine([1, 0], [0, 1]) == 0
    with pytest.raises(ValueError):
        module.cosine([1], [1, 2])
    with pytest.raises(ValueError):
        module.cosine([0, 0], [1, 1])
