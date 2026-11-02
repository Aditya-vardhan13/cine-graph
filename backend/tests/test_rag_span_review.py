from copy import deepcopy
import hashlib
import json

import pytest

from app.services.rag_span_review import bind_review_quotes, score_span_coverage, validate_review


def example():
    corpus = {"fingerprint": "fixed", "documents": [
        {"chunk_id": qid, "film_qid": qid, "content": "A choice has a cost."} for qid in ("A", "B")],
        "cases": [{"case_id": "C1", "film_qids": ["A", "B"], "question": "What is the cost?"},
                  {"case_id": "C2", "film_qids": ["A", "B"], "question": "Unreviewed?"}]}
    review = {"corpus_fingerprint": "fixed", "reviewer": "source-reviewer", "review_method": "manual",
        "cases": [{"case_id": "C1", "premise_status": "supported", "rationale": "Both describe cost.",
                   "facets": [{"id": "cost", "description": "Consequence of a choice"}],
                   "evidence": [{"chunk_id": qid, "film_qid": qid, "start": 0, "end": 20,
                                 "quote": "A choice has a cost.", "support": "direct",
                                 "facet_ids": ["cost"], "rationale": "Explicit consequence."}
                                for qid in ("A", "B")]}]}
    corpus["fingerprint"] = hashlib.sha256(json.dumps(
        {key: value for key, value in corpus.items() if key != "fingerprint"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()
    review["corpus_fingerprint"] = corpus["fingerprint"]
    for item in review["cases"][0]["evidence"]:
        item["end"] = len(item["quote"])
    return corpus, review


def test_exact_spans_and_both_film_facets_not_unknown_negatives():
    corpus, review = example()
    rankings = {"C1": {qid: [{"chunk_id": qid}] for qid in ("A", "B")}}
    result = score_span_coverage(corpus, review, rankings, k=1)
    assert result["both_films_covered"] == 1
    assert result["reviewed_supported_cases"] == 1
    assert result["total_frozen_cases"] == 2
    rankings["C1"]["B"][0]["end"] = 8
    assert score_span_coverage(corpus, review, rankings, k=1)["both_films_covered"] == 0
    with pytest.raises(ValueError, match="Missing rankings"):
        score_span_coverage(corpus, review, {}, k=1)


def test_rejects_invented_quotes_wrong_film_and_unlabeled_facets():
    corpus, review = example()
    wrong = deepcopy(review)
    wrong["cases"][0]["evidence"][0]["quote"] = "Invented evidence"
    with pytest.raises(ValueError, match="exact"):
        validate_review(corpus, wrong)
    wrong = deepcopy(review)
    wrong["cases"][0]["evidence"][0]["film_qid"] = "B"
    with pytest.raises(ValueError, match="selected film"):
        validate_review(corpus, wrong)
    review["cases"][0]["evidence"].pop()
    with pytest.raises(ValueError, match="every facet"):
        score_span_coverage(corpus, review, {"C1": {"A": [], "B": []}}, k=1)


def test_quote_authoring_compiles_unique_exact_offsets_without_inventing_labels():
    corpus, review = example()
    authored = deepcopy(review)
    for item in authored["cases"][0]["evidence"]:
        del item["start"], item["end"]
    assert bind_review_quotes(corpus, authored) == review
    assert "start" not in authored["cases"][0]["evidence"][0]
    authored["cases"][0]["evidence"][0]["quote"] = "absent"
    with pytest.raises(ValueError, match="exactly one"):
        bind_review_quotes(corpus, authored)


def test_conjunctive_source_group_requires_all_supporting_spans():
    corpus, review = example()
    first = review["cases"][0]["evidence"][0]
    first.update(quote="A choice", start=0, end=8, evidence_group="linked")
    second = {**first, "quote": "cost.", "start": 15, "end": 20}
    # Resolve offsets from the real fixture text, without changing its fingerprint.
    second["start"] = corpus["documents"][0]["content"].index("cost.")
    second["end"] = second["start"] + len("cost.")
    review["cases"][0]["evidence"].append(second)
    rankings = {"C1": {"A": [{"chunk_id": "A", "start": 0, "end": 8}], "B": [{"chunk_id": "B"}]}}
    assert score_span_coverage(corpus, review, rankings, k=2)["both_films_covered"] == 0
    rankings["C1"]["A"].append({"chunk_id": "A", "start": second["start"], "end": second["end"]})
    assert score_span_coverage(corpus, review, rankings, k=2)["both_films_covered"] == 1
