"""Reviewed source-span visibility; never a claim-truth or answer-quality score."""
from __future__ import annotations


def source_span_rank(review: dict, question: dict, documents: dict, ranked: list[dict]) -> int | None:
    """Return one-based first rank containing the entire reviewed source span."""
    if review["case_id"] != question["case_id"]:
        raise ValueError("Review and question do not match.")
    doc_id, quote = review["document_id"], review["quote"]
    if doc_id not in question["evidence_document_ids"] or doc_id not in documents:
        raise ValueError("Reviewed evidence is outside the question's source scope.")
    content = documents[doc_id]["content"]
    if not quote or content.count(quote) != 1:
        raise ValueError("Reviewed quote must occur exactly once in the source document.")
    start = content.index(quote)
    end = start + len(quote)
    seen = set()
    first_match = None
    for rank, candidate in enumerate(ranked, 1):
        identifier = candidate["passage_id"]
        candidate_doc = candidate["document_id"]
        if identifier in seen or candidate_doc not in question["evidence_document_ids"]:
            raise ValueError("Ranking has duplicate or out-of-scope evidence.")
        seen.add(identifier)
        if candidate_doc not in documents:
            raise ValueError("Ranking source is missing.")
        left, right = candidate["start"], candidate["end"]
        if type(left) is not int or type(right) is not int or not 0 <= left < right <= len(documents[candidate_doc]["content"]):
            raise ValueError("Ranked passage has invalid offsets.")
        if first_match is None and candidate_doc == doc_id and left <= start and right >= end:
            first_match = rank
    return first_match
