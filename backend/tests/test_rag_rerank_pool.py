from copy import deepcopy

import pytest

from app.services.rag_dense_trial import digest
from app.services.rag_rerank_pool import prepare_dense_pool, prepare_pool


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


def test_dense_pool_adapter_retains_provenance_and_rejects_partial_parent():
    corpus={"documents":[{"chunk_id":qid,"film_qid":qid,"content":"Source text",
        "source_snapshot_id":"revision","film_title":qid,"section_title":"Plot"}
        for qid in ("A","B")],"cases":[{"case_id":"c","film_qids":["A","B"],"question":"Why?"}]}
    corpus["fingerprint"]=digest(corpus)
    dense={"contract":{"corpus":corpus["fingerprint"],"representation":"source-full-parent-v1"},
        "cases":[{"case_id":"c","question":"Why?","sides":[{"film_qid":qid,
            "ranked":[{"chunk_id":qid,"film_qid":qid,"text":"Source text","start":0,
                "end":11,"source_snapshot_id":"revision"}]} for qid in ("A","B")]}]}
    result=prepare_dense_pool(corpus,dense)
    assert result["cases"][0]["first_pool"][0]==corpus["documents"][0]
    assert result["dense_ranking_sha256"]==digest(dense)
    dense["cases"][0]["sides"][0]["ranked"][0]["end"]=10
    with pytest.raises(ValueError,match="source span"):
        prepare_dense_pool(corpus,dense)
