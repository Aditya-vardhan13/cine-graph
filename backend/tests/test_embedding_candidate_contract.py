import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "candidate_contract", Path(__file__).resolve().parents[2] / "scripts/check_embedding_candidate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_vector_contract_requires_finite_nonzero_and_expected_shape():
    assert module.vector_statistics([[0.6, 0.8]], 2) == [1.0]
    for vectors in ([], [[0.0, 0.0]], [[float("nan"), 1.0]],
                    [[float("inf"), 1.0]], [[1.0]]):
        with pytest.raises(ValueError):
            module.vector_statistics(vectors, 2)
