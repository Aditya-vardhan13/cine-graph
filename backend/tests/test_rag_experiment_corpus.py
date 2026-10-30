import pytest

from app.services.rag_experiment_corpus import bind_corpus


def test_fingerprint_binds_sources_questions_and_parent_context_not_input_order():
    documents = [{"chunk_id": "b", "film_qid": "Q2", "parent_content": "Later choice"},
                 {"chunk_id": "a", "film_qid": "Q1", "parent_content": "Initial choice"}]
    cases = [{"film_qids": ["Q1", "Q2"], "question": "What changes?"}]
    first = bind_corpus(collection="canary", run_id="run", documents=documents, cases=cases)
    assert first == bind_corpus(collection="canary", run_id="run", documents=documents[::-1], cases=cases)
    changed = [{**row, "parent_content": "changed"} for row in documents]
    assert first["fingerprint"] != bind_corpus(collection="canary", run_id="run", documents=changed, cases=cases)["fingerprint"]
    with pytest.raises(ValueError, match="distinct"):
        bind_corpus(collection="canary", run_id="run", documents=documents * 2, cases=cases)
    with pytest.raises(ValueError, match="both"):
        bind_corpus(collection="canary", run_id="run", documents=documents[:1], cases=cases)
