from copy import deepcopy

import pytest

from app.services.rag_dense_trial import digest
from app.services.rag_rerank_pool import prepare_pool


def test_rerank_pool_binds_exact_questions_films_and_source_text():
    corpus = {"documents": [{"chunk_id": qid, "film_qid": qid, "content": "Source text",
                              "source_snapshot_id": "revision"} for qid in ("A", "B")],
              "cases": [{"case_id": "C1", "film_qids": ["A", "B"], "question": "Why?"}]}
    corpus["fingerprint"] = digest(corpus)
    case = {**corpus["cases"][0], "titles": ["First film", "Second film"]}
    for side, qid in (("first", "A"), ("second", "B")):
        case[f"{side}_pool"] = [{"chunk_id": qid, "content": "Source text", "source_snapshot_id": "revision"}]
    trial = {"cases": [case]}
    assert prepare_pool(corpus, trial)["cases"][0]["first_pool"] == case["first_pool"]
    changed = deepcopy(trial)
    changed["cases"][0]["first_pool"][0]["content"] = "Invented text"
    with pytest.raises(ValueError, match="source identity"):
        prepare_pool(corpus, changed)
    changed = deepcopy(trial)
    changed["cases"][0]["question"] = "Different question"
    with pytest.raises(ValueError, match="drifted"):
        prepare_pool(corpus, changed)
