"""Conservative identity classification; candidates are not reviewed resolutions."""
import re


def match_summary_identity(document: dict, catalog_by_qid: dict) -> dict:
    ids = sorted({identity.get("wikidata_id") for identity in document["identities"] if identity.get("wikidata_id")})
    base = {"document_id": document["document_id"], "source_qids": ids,
            "operational_eligible": False, "review_status": "review_required"}
    if not ids:
        return {**base, "match_status": "missing_source_id"}
    if len(ids) != 1 or not re.fullmatch(r"Q[1-9][0-9]*", ids[0]):
        return {**base, "match_status": "ambiguous_or_invalid_source_id"}
    film = catalog_by_qid.get(ids[0])
    if film is None:
        return {**base, "match_status": "no_catalog_film_with_qid"}
    return {**base, "match_status": "exact_qid_candidate", "catalog_film_id": str(film["id"]),
            "catalog_title": film["canonical_title"], "catalog_review_status": film["review_status"]}
