import pytest

from app.services.mf2_span_diagnostic import source_span_rank


def test_reviewed_complete_span_not_keyword_overlap_determines_rank():
    docs = {"A": {"content": "A person wants to buy a home and accepts the job."}, "B": {"content": "A home exists."}}
    question = {"case_id": "x", "evidence_document_ids": ["A", "B"]}
    review = {"case_id": "x", "document_id": "A", "quote": "buy a home and accepts the job"}
    ranked = [{"passage_id": "b", "document_id": "B", "start": 0, "end": len(docs["B"]["content"])},
              {"passage_id": "a", "document_id": "A", "start": 0, "end": len(docs["A"]["content"])}]
    assert source_span_rank(review, question, docs, ranked) == 2
    assert source_span_rank(review, question, docs, ranked[:1]) is None
    with pytest.raises(ValueError, match="duplicate"):
        source_span_rank(review, question, docs, [ranked[1], ranked[1]])


def test_review_must_be_unique_and_source_scoped():
    docs = {"A": {"content": "same same"}}
    with pytest.raises(ValueError, match="exactly once"):
        source_span_rank({"case_id": "x", "document_id": "A", "quote": "same"},
                         {"case_id": "x", "evidence_document_ids": ["A"]}, docs, [])
    with pytest.raises(ValueError, match="outside"):
        source_span_rank({"case_id": "x", "document_id": "A", "quote": "same same"},
                         {"case_id": "x", "evidence_document_ids": ["B"]}, docs, [])
