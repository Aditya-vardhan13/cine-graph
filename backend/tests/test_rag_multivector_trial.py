import numpy as np
import pytest

from app.services.rag_multivector_trial import mean_maxsim


def test_maxsim_matches_each_query_token_not_mean_passage_embedding():
    query = np.eye(2, dtype=np.float32)
    passage = np.asarray([[1., 0.], [0., 1.], [-1., 0.]])
    assert mean_maxsim(query, passage) == 1
    assert mean_maxsim(query, passage[:1]) == 0.5
    assert mean_maxsim(query, passage[::-1]) == 1


def test_maxsim_rejects_empty_or_invalid_vectors():
    for query, passage in ((np.zeros((0, 2)), np.eye(2)), (np.eye(2), np.eye(3)),
                           (np.asarray([[np.nan, 0.]]), np.eye(2))):
        with pytest.raises(ValueError):
            mean_maxsim(query, passage)
