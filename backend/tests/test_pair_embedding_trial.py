from uuid import uuid4

import numpy as np
import pytest

from app.models import EvidenceChunk
from app.services.pair_embedding_trial import rank_film_candidates, trial_question_texts


def test_film_context_queries_keep_frozen_order_and_original_question():
    rows = [({"titles": ["Her", "WALL-E"]}, 1, "How does the relationship begin?")]
    assert trial_question_texts(rows, film_context=False) == ["How does the relationship begin?"]
    assert trial_question_texts(rows, film_context=True) == [
        "Film: Her\nResearch question: How does the relationship begin?",
        "Film: WALL-E\nResearch question: How does the relationship begin?",
    ]


def _chunk(subject_id, content):
    return EvidenceChunk(
        id=uuid4(),
        subject_entity_id=subject_id,
        source_snapshot_id=uuid4(),
        section_locator="Plot",
        section_title="Plot",
        content=content,
    )


def test_pair_embedding_ranking_is_film_scoped_and_cosine_ordered():
    film_id = uuid4()
    other_film_id = uuid4()
    chunks = [
        _chunk(film_id, "direct evidence"),
        _chunk(film_id, "unrelated evidence"),
        _chunk(other_film_id, "highly similar but outside film scope"),
    ]
    matrix = np.asarray([[1.0, 0.0], [0.0, 1.0], [0.99, 0.01]], dtype=np.float32)

    ranked = rank_film_candidates(
        film_entity_id=str(film_id),
        chunks=chunks,
        matrix=matrix,
        query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
        limit=10,
    )

    assert [item["chunk_id"] for item in ranked] == [str(chunks[0].id), str(chunks[1].id)]
    assert all(item["subject_entity_id"] == str(film_id) for item in ranked)
    assert ranked[0]["semantic_similarity"] == 1.0


def test_pair_embedding_ranking_rejects_vector_shape_mismatch():
    film_id = uuid4()
    chunks = [_chunk(film_id, "evidence")]

    with pytest.raises(ValueError, match="dimensions must match"):
        rank_film_candidates(
            film_entity_id=str(film_id),
            chunks=chunks,
            matrix=np.asarray([[1.0, 0.0]], dtype=np.float32),
            query_vector=np.asarray([1.0], dtype=np.float32),
            limit=1,
        )


def test_pair_embedding_ranking_rejects_zero_norm_vectors():
    film_id = uuid4()

    with pytest.raises(ValueError, match="Zero-length embeddings"):
        rank_film_candidates(
            film_entity_id=str(film_id),
            chunks=[_chunk(film_id, "evidence")],
            matrix=np.asarray([[0.0, 0.0]], dtype=np.float32),
            query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            limit=1,
        )
