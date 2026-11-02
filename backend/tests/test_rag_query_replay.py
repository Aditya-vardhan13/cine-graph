from copy import deepcopy

import numpy as np
import pytest

from app.services.embedding_artifacts import document_cache_key
from app.services.ollama_embeddings import OllamaEmbeddingProfile
from app.services.rag_dense_trial import digest
from app.services.rag_query_plan import PLANNER_VERSION
from app.services.rag_query_replay import fuse_branches, load_documents, validate_plans


def test_branch_fusion_preserves_original_and_diversifies_without_duplicates():
    branches = [[{"chunk_id": key} for key in ids] for ids in (["a", "b", "c"], ["b", "d", "a"])]
    assert [r["chunk_id"] for r in fuse_branches(branches, limit=3, policy="original")] == ["a", "b", "c"]
    assert [r["chunk_id"] for r in fuse_branches(branches, limit=4, policy="round-robin")] == ["a", "b", "d", "c"]
    assert [r["chunk_id"] for r in fuse_branches(branches, limit=4, policy="rrf")] == ["b", "a", "d", "c"]


def test_duplicate_source_and_unknown_policy_fail():
    with pytest.raises(ValueError):
        fuse_branches([[{"chunk_id": "a"}, {"chunk_id": "a"}]], limit=2, policy="rrf")
    with pytest.raises(ValueError):
        fuse_branches([], limit=2, policy="rrf")


def example():
    corpus = {"chunk_run_id": "retained-run", "documents": [
        {"chunk_id": "a", "film_qid": "A", "film_title": "Film A", "section_title": "Plot",
         "content": "A choice has consequences."}],
        "cases": [{"case_id": "C1", "question": "Which choice has consequences?", "film_qids": ["A", "B"]}]}
    corpus["fingerprint"] = digest(corpus)
    plans = {"complete": True, "contract": {"planner_version": PLANNER_VERSION}, "cases": [
        {"case_id": "C1", "question": corpus["cases"][0]["question"],
         "queries": [corpus["cases"][0]["question"], "choice"], "valid_schema": True}]}
    return corpus, plans


def test_replay_rejects_modified_corpus_questions_or_generated_meanings():
    corpus, plans = example()
    assert validate_plans(corpus, plans)["C1"][-1] == "choice"
    wrong = deepcopy(corpus)
    wrong["documents"][0]["content"] = "Changed source."
    with pytest.raises(ValueError, match="fingerprint"):
        validate_plans(wrong, plans)
    for field, value in (("question", "Another question"), ("queries", ["Which choice has consequences?", "betrayal"])):
        wrong = deepcopy(plans)
        wrong["cases"][0][field] = value
        with pytest.raises(ValueError):
            validate_plans(corpus, wrong)
    plans["complete"] = False
    with pytest.raises(ValueError, match="complete"):
        validate_plans(corpus, plans)


def test_matrix_cache_binds_exact_document_order_and_content(tmp_path):
    corpus, _ = example()
    profile = OllamaEmbeddingProfile(model="qwen3-embedding:4b", dimensions=2)
    key = document_cache_key(provider="ollama", model_name=profile.model, dimensions=2,
        chunk_run_id="retained-run", chunker_version="version",
        contents=["Film: Film A\nSection: Plot\nEvidence: A choice has consequences."])
    path = tmp_path / f"qwen3-embedding--4b-{key}.npy"
    np.save(path, [[1., 0.]])
    docs, matrix = load_documents(corpus, path, profile=profile, chunker_version="version")
    assert matrix.shape == (1, 2)
    assert docs[0]["text"] == corpus["documents"][0]["content"]
    with pytest.raises(ValueError, match="identity"):
        load_documents(corpus, path, profile=profile, chunker_version="changed")
    np.save(path, [[float("nan"), 0.]])
    with pytest.raises(ValueError, match="values"):
        load_documents(corpus, path, profile=profile, chunker_version="version")
