"""Pure fixed-pool fusion safety checks."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from score_recovery_small_reranker import fuse_ranks


def test_fusion_preserves_pool_and_uses_stable_dense_tiebreak():
    assert fuse_ranks(['a','b'],['b','a'],dense_weight=1,small_weight=1)==['a','b']
    assert set(fuse_ranks(['a','b','c'],['c','a','b'],dense_weight=3,small_weight=1))=={'a','b','c'}


def test_fusion_rejects_inconsistent_or_duplicate_candidates():
    for a,b in ((['a','a'],['a','b']),(['a','b'],['a','a']),(['a'],['b'])):
        with pytest.raises(ValueError): fuse_ranks(a,b,dense_weight=1,small_weight=1)
