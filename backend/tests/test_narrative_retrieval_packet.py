import pytest

from app.services.narrative_retrieval_packet import diagnostic_dev_film, rank_claim


def test_scope_and_query_change_the_ranked_leads_without_labels():
    documents = [{"document_id": identity, "passage_id": identity + str(i), "start": 0,
                  "end": len(content), "content": content}
                 for i, (identity, content) in enumerate((
                     ("mf2:1:transcript", "A family protects a child."),
                     ("mf2:1:synopsis", "A detective investigates a missing painting."),
                     ("mf2:2:transcript", "A family protects a child.")))]
    query = {"case_id": "x", "task": "claim_verification", "claim": "family child",
             "evidence_document_ids": ["mf2:1:transcript", "mf2:1:synopsis"]}
    first = rank_claim(query, documents, top_k=1)
    second = rank_claim({**query, "claim": "detective painting"}, documents, top_k=1)
    assert first["ranked"][0]["document_id"] == "mf2:1:transcript"
    assert second["ranked"][0]["document_id"] == "mf2:1:synopsis"
    assert first["candidate_count"] == 2
    with pytest.raises(ValueError, match="missing"):
        rank_claim(query, documents[1:])


def test_diagnostic_split_is_deterministic_and_film_scoped():
    assert diagnostic_dev_film("mf2:1:transcript") == diagnostic_dev_film("mf2:1:synopsis")
    membership = [diagnostic_dev_film(f"mf2:{i}:transcript") for i in range(1, 54)]
    assert 0 < sum(membership) < len(membership)
    with pytest.raises(ValueError):
        diagnostic_dev_film("Q1")
