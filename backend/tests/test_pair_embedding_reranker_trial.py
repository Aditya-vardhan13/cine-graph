import numpy as np
import pytest

from app.services.pair_embedding_reranker_trial import (
    rank_candidate_union,
    restrict_to_reviewed_candidates,
)


def _capture_and_vectors():
    cases = []
    chunks = []
    vectors = []
    for index in range(50):
        first_id = f"first-{index}"
        second_id = f"second-{index}"
        cases.append({
            "case_id": f"P{index:02}-Q1",
            "question": f"Question {index}",
            "film_qids": [f"Q{index}A", f"Q{index}B"],
            "first_pool": [{"chunk_id": first_id, "section_title": "Plot"}],
            "second_pool": [{"chunk_id": second_id, "section_title": "Plot"}],
        })
        chunks.extend([{"chunk_id": first_id}, {"chunk_id": second_id}])
        vectors.extend([[1.0, 0.0], [0.0, 1.0]])
    return {"method": "candidate-union", "cases": cases}, chunks, vectors


def test_embedding_ranker_returns_complete_film_side_rankings():
    capture, chunks, vectors = _capture_and_vectors()
    ranking = rank_candidate_union(
        capture,
        chunks=chunks,
        matrix=np.asarray(vectors, dtype=np.float32),
        query_vectors=[[1.0, 0.0] for _ in range(50)],
    )

    assert ranking["complete"] is True
    assert len(ranking["cases"]) == 50
    assert all(case["first_ranking"][0]["chunk_id"] == f"first-{index}"
               for index, case in enumerate(ranking["cases"]))
    assert all(case["second_ranking"][0]["chunk_id"] == f"second-{index}"
               for index, case in enumerate(ranking["cases"]))


def test_embedding_ranker_rejects_missing_question_vectors():
    capture, chunks, vectors = _capture_and_vectors()

    with pytest.raises(ValueError, match="one vector per question"):
        rank_candidate_union(
            capture,
            chunks=chunks,
            matrix=np.asarray(vectors, dtype=np.float32),
            query_vectors=[[1.0, 0.0]],
        )


def test_embedding_ranker_rejects_zero_norm_query():
    capture, chunks, vectors = _capture_and_vectors()
    query_vectors = [[1.0, 0.0] for _ in range(50)]
    query_vectors[0] = [0.0, 0.0]

    with pytest.raises(ValueError, match="Zero-length query"):
        rank_candidate_union(
            capture,
            chunks=chunks,
            matrix=np.asarray(vectors, dtype=np.float32),
            query_vectors=query_vectors,
        )


def test_review_packet_restriction_keeps_only_reviewed_passages_per_film_side():
    capture = {
        "method": "candidate-union",
        "cases": [{
            "case_id": "P01-Q1",
            "film_qids": ["Q1", "Q2"],
            "first_pool": [{"chunk_id": "a"}, {"chunk_id": "b"}],
            "second_pool": [{"chunk_id": "c"}, {"chunk_id": "d"}],
            "first_options": [{"chunk_id": "a"}],
            "second_options": [{"chunk_id": "c"}],
        }],
    }
    packet = {"items": [
        {"key": "P01-Q1|Q1|b"},
        {"key": "P01-Q1|Q2|d"},
    ]}

    restricted = restrict_to_reviewed_candidates(capture, packet)

    assert [x["chunk_id"] for x in restricted["cases"][0]["first_pool"]] == ["b"]
    assert [x["chunk_id"] for x in restricted["cases"][0]["second_pool"]] == ["d"]
    assert capture["cases"][0]["first_pool"] == [{"chunk_id": "a"}, {"chunk_id": "b"}]


def test_review_packet_restriction_rejects_unknown_chunk():
    capture = {
        "cases": [{
            "case_id": "P01-Q1", "film_qids": ["Q1", "Q2"],
            "first_pool": [{"chunk_id": "a"}], "second_pool": [{"chunk_id": "b"}],
        }],
    }

    with pytest.raises(ValueError, match="candidates do not match"):
        restrict_to_reviewed_candidates(capture, {"items": [{"key": "P01-Q1|Q1|missing"}]})
