"""Content-bound facet/span review policies, not an automated entailment judge."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy


def bind_review_quotes(corpus: dict, authored: dict) -> dict:
    """Compile human-authored exact quotations to source offsets; never infer labels."""
    review = deepcopy(authored)
    documents = {row["chunk_id"]: row for row in corpus["documents"]}
    for case in review["cases"]:
        for evidence in case["evidence"]:
            if "start" in evidence or "end" in evidence:
                continue
            doc = documents.get(evidence["chunk_id"])
            quote = evidence["quote"]
            if doc is None or not quote or doc["content"].count(quote) != 1:
                raise ValueError("Authored quotation must identify exactly one source span.")
            evidence["start"] = doc["content"].index(quote)
            evidence["end"] = evidence["start"] + len(quote)
    validate_review(corpus, review)
    return review


def validate_review(corpus: dict, review: dict) -> None:
    actual = hashlib.sha256(json.dumps(
        {key: value for key, value in corpus.items() if key != "fingerprint"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()
    if actual != corpus.get("fingerprint"):
        raise ValueError("Frozen corpus content failed its fingerprint.")
    if review.get("corpus_fingerprint") != corpus.get("fingerprint"):
        raise ValueError("Review must bind the frozen corpus fingerprint.")
    if not review.get("reviewer") or not review.get("review_method"):
        raise ValueError("Reviewer identity and method are required.")
    documents = {row["chunk_id"]: row for row in corpus["documents"]}
    questions = {row["case_id"]: row for row in corpus["cases"]}
    seen = set()
    for case in review["cases"]:
        case_id = case["case_id"]
        if case_id not in questions or case_id in seen:
            raise ValueError("Every reviewed case must be a unique frozen question.")
        seen.add(case_id)
        if case["premise_status"] not in {"supported", "unsupported", "uncertain"}:
            raise ValueError("Question premise status is required.")
        facets = {row["id"] for row in case["facets"] if row.get("description", "").strip()}
        if not facets or len(facets) != len(case["facets"]):
            raise ValueError("Question facets require distinct IDs and descriptions.")
        if not case.get("rationale", "").strip():
            raise ValueError("A source-aware case rationale is required.")
        for evidence in case["evidence"]:
            doc = documents.get(evidence["chunk_id"])
            if (doc is None or doc["film_qid"] != evidence["film_qid"] or
                    evidence["film_qid"] not in questions[case_id]["film_qids"]):
                raise ValueError("Supporting span must belong to the selected film.")
            start, end = evidence["start"], evidence["end"]
            if (type(start) is not int or type(end) is not int or
                    not 0 <= start < end <= len(doc["content"]) or
                    doc["content"][start:end] != evidence["quote"]):
                raise ValueError("Supporting quote must match exact source offsets.")
            if (evidence["support"] not in {"direct", "partial"} or
                    not evidence.get("rationale", "").strip() or
                    not evidence["facet_ids"] or not set(evidence["facet_ids"]).issubset(facets)):
                raise ValueError("Every span needs valid facet labels, support and rationale.")
            if "evidence_group" in evidence and not str(evidence["evidence_group"]).strip():
                raise ValueError("Evidence group labels cannot be empty.")


def score_span_coverage(corpus: dict, review: dict, rankings: dict, *, k: int) -> dict:
    """Score reviewed supported premises only; omitted labels are not negatives.

    A retrieved window must contain a full reviewed quote. This checks source
    visibility, not whether a generated answer is correct or creatively useful.
    """
    validate_review(corpus, review)
    if k < 1:
        raise ValueError("k must be positive.")
    documents = {row["chunk_id"]: row for row in corpus["documents"]}
    questions = {row["case_id"]: row for row in corpus["cases"]}
    rows = []
    for case in review["cases"]:
        if case["premise_status"] != "supported":
            continue
        sides = []
        for qid in questions[case["case_id"]]["film_qids"]:
            positives = [item for item in case["evidence"]
                         if item["film_qid"] == qid and item["support"] == "direct"]
            expected = {facet["id"] for facet in case["facets"]}
            labeled = {facet for item in positives for facet in item["facet_ids"]}
            if labeled != expected:
                raise ValueError("Supported cases need direct source spans for every facet in both films.")
            candidates = rankings.get(case["case_id"], {}).get(qid)
            if candidates is None:
                raise ValueError("Missing rankings cannot silently score as a retrieval failure.")
            covered, hits = set(), set()
            for candidate in candidates[:k]:
                doc = documents.get(candidate["chunk_id"])
                if doc is None or doc["film_qid"] != qid:
                    raise ValueError("Ranking contains evidence from the wrong film or corpus.")
                start = candidate.get("start", 0)
                end = candidate.get("end", len(doc["content"]))
                if not 0 <= start < end <= len(doc["content"]):
                    raise ValueError("Ranked window offsets are invalid.")
                for index, item in enumerate(positives):
                    if item["chunk_id"] == candidate["chunk_id"] and start <= item["start"] and end >= item["end"]:
                        hits.add(index)
            groups = {}
            for index, item in enumerate(positives):
                groups.setdefault(item.get("evidence_group", f"single:{index}"), []).append(index)
            for indexes in groups.values():
                if all(index in hits for index in indexes):
                    covered.update(facet for index in indexes for facet in positives[index]["facet_ids"])
            sides.append({"film_qid": qid, "covered_facets": sorted(covered),
                          "required_facets": sorted(expected), "complete": covered == expected})
        rows.append({"case_id": case["case_id"], "sides": sides,
                     "both_films_covered": all(side["complete"] for side in sides)})
    return {"k": k, "reviewed_supported_cases": len(rows),
            "total_frozen_cases": len(corpus["cases"]),
            "both_films_covered": sum(row["both_films_covered"] for row in rows),
            "cases": rows,
            "caution": "Source-span visibility only; incomplete reviews and uncertain premises are not a quality score."}
