from copy import deepcopy

import pytest

from app.services.rag_dense_trial import digest
from app.services.rag_source_rebinding_audit import audit_rebinding


def example():
    case = {"case_id": "C", "question": "What changes?", "film_qids": ["A", "B"]}
    documents = [{"chunk_id": qid, "film_qid": qid, "source_snapshot_id": f"snapshot-{qid}",
                  "content": "The character makes a choice."} for qid in ("A", "B")]
    corpus = {"documents": documents, "cases": [case]}
    corpus["fingerprint"] = digest(corpus)
    review = {"corpus_fingerprint": corpus["fingerprint"], "reviewer": "fixture", "review_method": "manual",
        "cases": [{"case_id": "C", "premise_status": "supported", "rationale": "A choice is explicit.",
            "facets": [{"id": "choice", "description": "A choice"}],
            "evidence": [{"chunk_id": qid, "film_qid": qid, "quote": "makes a choice",
                          "support": "direct", "facet_ids": ["choice"], "rationale": "Explicit"} for qid in ("A", "B")]}]}
    return corpus, review


def test_exact_quote_matches_are_candidates_not_promoted_labels():
    corpus, review = example()
    result = audit_rebinding(corpus, corpus, review)
    assert result["summary"] == {"unique": 2, "missing": 0, "ambiguous": 0}
    assert result["status"] == "candidate-locations-only-not-reviewed-labels"
    assert "cases" not in result


def test_source_revision_or_duplicate_quote_is_not_silently_accepted():
    corpus, review = example()
    target = deepcopy(corpus)
    target["documents"][0]["source_snapshot_id"] = "different-snapshot"
    target["documents"][1]["content"] += " makes a choice"
    target["fingerprint"] = digest({k: v for k, v in target.items() if k != "fingerprint"})
    assert audit_rebinding(corpus, target, review)["summary"] == {"unique": 0, "missing": 1, "ambiguous": 1}
    target["cases"][0]["question"] = "Changed question?"
    target["fingerprint"] = digest({k: v for k, v in target.items() if k != "fingerprint"})
    with pytest.raises(ValueError, match="same frozen"):
        audit_rebinding(corpus, target, review)
