import numpy as np
import pytest

from app.services.rag_dense_trial import pack_parent_context, rank_windows, source_windows


def test_windows_preserve_exact_source_spans_and_cover_tail():
    text = "Alpha  beta\ngamma delta epsilon zeta eta"
    windows = source_windows(text, words=4, overlap=1)
    assert all(row["text"] == text[row["start"]:row["end"]] for row in windows)
    assert windows[0]["text"] == "Alpha  beta\ngamma delta"
    assert windows[-1]["text"].endswith("eta")
    assert source_windows("") == []
    with pytest.raises(ValueError):
        source_windows(text, words=4, overlap=4)


def test_rank_uses_film_scope_cosine_and_stable_ties():
    docs = [{"window_id": key, "film_qid": film} for key, film in (("b", "Q1"), ("a", "Q1"), ("c", "Q2"))]
    matrix = np.asarray([[1., 0.], [2., 0.], [1., 1.]])
    ranked = rank_windows(docs, matrix, np.asarray([1., 0.]), film_qid="Q1")
    assert [row["window_id"] for row in ranked] == ["a", "b"]
    with pytest.raises(ValueError, match="zero"):
        rank_windows(docs, matrix, np.zeros(2), film_qid="Q1")
    with pytest.raises(ValueError, match="dimensions"):
        rank_windows(docs, matrix, np.zeros(3), film_qid="Q1")


def test_parent_context_preserves_source_and_reports_budget_omissions():
    corpus = {"documents": [{"chunk_id": key, "film_qid": "Q1", "content": text,
                              "source_snapshot_id": "revision"}
                             for key, text in (("A", "Full parent."), ("B", "Another parent."))]}
    ranked = [{"chunk_id": "A", "start": 2, "end": 6}, {"chunk_id": "A"}, {"chunk_id": "B"}]
    packed = pack_parent_context(corpus, ranked, film_qid="Q1", character_budget=15)
    assert len(packed["parents"]) == 1
    assert packed["parents"][0]["text"] == "Full parent."
    assert packed["parents"][0]["retrieved_anchor"] == ranked[0]
    assert packed["omitted"] == [{"chunk_id": "B", "reason": "context_budget"}]
    with pytest.raises(ValueError, match="outside"):
        pack_parent_context(corpus, ranked, film_qid="Q2")
