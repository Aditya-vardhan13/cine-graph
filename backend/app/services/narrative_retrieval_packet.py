"""Label-blind claim-evidence ranking; scores are leads, never truth judgments."""
from __future__ import annotations

from app.services.external_narrative_preparation import text_id
from app.services.lexical_retrieval import Bm25Index


def diagnostic_dev_film(document_id: str) -> bool:
    parts = document_id.split(":")
    if len(parts) != 3 or parts[0] != "mf2" or not parts[1].isdigit():
        raise ValueError("Expected a dataset-local MF2 document identity.")
    return int(text_id(f"mf2-diagnostic-split-v1:{parts[1]}")[:8], 16) % 5 == 0


def rank_claim(question: dict, passages: list[dict], *, top_k: int = 6) -> dict:
    if top_k < 1 or question["task"] != "claim_verification":
        raise ValueError("This packet is only a bounded claim-retrieval diagnostic.")
    allowed = set(question["evidence_document_ids"])
    if len(allowed) != 2:
        raise ValueError("Both transcript and synopsis sources must be present.")
    candidates = sorted((p for p in passages if p["document_id"] in allowed), key=lambda p: p["passage_id"])
    if {p["document_id"] for p in candidates} != allowed:
        raise ValueError("Claim evidence is missing from the supplied passages.")
    scores = Bm25Index.build(p["content"] for p in candidates).scores(question["claim"])
    order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i]["passage_id"]))
    return {"case_id": question["case_id"], "claim": question["claim"],
            "evidence_document_ids": sorted(allowed), "candidate_count": len(candidates),
            "ranked": [{"passage_id": candidates[i]["passage_id"], "document_id": candidates[i]["document_id"],
                        "start": candidates[i]["start"], "end": candidates[i]["end"], "score": scores[i]}
                       for i in order[:top_k]],
            "caution": "Question-conditioned research leads; relevance and claim support need review."}
