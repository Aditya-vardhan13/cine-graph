"""Check token-prefix boundaries without substituting an inference model."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from benchmark_reranker_prefix_cache import common_prefix


def test_common_prefix_uses_actual_token_ids():
    assert common_prefix([[1,2,3],[1,2,4],[1,2,5,6]]) == [1,2]
    assert common_prefix([[1],[2]]) == []
    assert common_prefix([[1,2],[1,2,3]]) == [1,2]


def test_common_prefix_requires_nonempty_sequences():
    for inputs in ([],[[]],[[1],[]]):
        with pytest.raises(ValueError,match="nonempty"):
            common_prefix(inputs)
