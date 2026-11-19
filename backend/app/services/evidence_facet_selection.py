"""Experimental evidence packing, not an entailment or answerability classifier."""
from __future__ import annotations

NARRATIVE_HEADINGS = frozenset({"plot", "synopsis", "story", "plot summary", "storyline"})


def select_evidence_leads(ranked: list[dict], parents: dict[str, dict], *,
                          film_qid: str, limit: int = 5,
                          require_narrative_lead: bool = False) -> dict:
    """Reserve one narrative lead on explicit request, without deleting context.

    Callers decide the required evidence facet; this function does not infer
    intent or claim any selected passage answers a question. No score threshold
    is invented to turn a candidate into proven evidence.
    """
    if limit < 1:
        raise ValueError("positive_limit_required")
    pool, seen = [], set()
    for rank, item in enumerate(ranked, 1):
        parent = parents.get(item["chunk_id"])
        if parent is None or parent["film_qid"] != film_qid or item["film_qid"] != film_qid:
            raise ValueError("candidate_outside_film_or_corpus")
        if item["chunk_id"] in seen:
            continue
        seen.add(item["chunk_id"])
        pool.append({**item, "dense_rank": rank, "section_title": parent["section_title"],
                     "selection_reason": "dense_rank", "support_validated": False})
    selected = pool[:limit]
    missing = []
    if require_narrative_lead:
        def narrative(item):
            return item["section_title"].split("/")[0].strip().casefold() in NARRATIVE_HEADINGS
        if not any(narrative(item) for item in selected):
            candidate = next((item for item in pool if narrative(item)), None)
            if candidate is None:
                missing.append("narrative_lead_not_in_candidate_pool")
            else:
                selected = selected[:max(0, limit-1)] + [
                    {**candidate, "selection_reason": "explicit_narrative_facet_reserve"}]
    return {"selected": selected, "missing_facets": missing,
            "policy": "explicit-facet-reserve-v1", "support_validated": False}
