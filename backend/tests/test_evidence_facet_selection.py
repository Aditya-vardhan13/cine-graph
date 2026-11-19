import pytest
from app.services.evidence_facet_selection import select_evidence_leads


def test_explicit_facet_keeps_context_without_claiming_support():
    parents = {"a": {"film_qid": "Q1", "section_title": "Production / Animation"},
               "b": {"film_qid": "Q1", "section_title": "Themes"},
               "c": {"film_qid": "Q1", "section_title": "Plot"}}
    ranked = [{"chunk_id": k, "film_qid": "Q1"} for k in parents]
    plain = select_evidence_leads(ranked, parents, film_qid="Q1", limit=2)
    assert [r["chunk_id"] for r in plain["selected"]] == ["a", "b"]
    reserved = select_evidence_leads(ranked, parents, film_qid="Q1", limit=2, require_narrative_lead=True)
    assert [r["chunk_id"] for r in reserved["selected"]] == ["a", "c"]
    assert reserved["selected"][1]["dense_rank"] == 3
    assert not any(r["support_validated"] for r in reserved["selected"])
    with pytest.raises(ValueError):
        select_evidence_leads(ranked, parents, film_qid="Q2")


def test_missing_facet_is_reported_not_fabricated():
    p = {"a": {"film_qid": "Q1", "section_title": "Production"}}
    r = [{"chunk_id": "a", "film_qid": "Q1"}]
    result = select_evidence_leads(r, p, film_qid="Q1", require_narrative_lead=True)
    assert result["missing_facets"] == ["narrative_lead_not_in_candidate_pool"]
