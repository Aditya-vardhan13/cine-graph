"""Score retained 4B/lexical leads against source-bound development spans.

This is a conservative span-inclusion diagnostic, not answer accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.corpus_build_manifest import canonical_digest
from evaluate_question_section_reserve import requested_section


def reserve_sections(ranked: list[dict], question: str, *, default_plot: bool = False) -> list[dict]:
    """Apply the previously inspected question-only development policy."""
    section = requested_section(question) or ("plot" if default_plot else None)
    if section is None:
        return list(ranked)
    def matches(item: dict) -> bool:
        return item["section_title"].split("/")[0].strip().casefold() == section
    selected = list(ranked[:5])
    for item in ranked[5:]:
        if sum(matches(candidate) for candidate in selected) >= 2:
            break
        if matches(item):
            replace = next((i for i in range(len(selected) - 1, -1, -1) if not matches(selected[i])), None)
            if replace is not None:
                selected[replace] = item
    selected_ids = {item["chunk_id"] for item in selected}
    return selected + [item for item in ranked if item["chunk_id"] not in selected_ids]


def reciprocal_rank_fusion(semantic: list[dict], lexical: list[dict]) -> list[dict]:
    """Equal-weight RRF over the two retained, film-scoped top-20 lists."""
    items = {}
    scores = {}
    for ranking in (semantic, lexical):
        seen = set()
        for rank, item in enumerate(ranking, 1):
            chunk = item["chunk_id"]
            if chunk in seen:
                raise ValueError("duplicate_ranked_chunk")
            seen.add(chunk)
            if chunk in items and any(items[chunk][key] != item[key] for key in
                    ("content", "subject_entity_id", "source_snapshot_id")):
                raise ValueError("conflicting_fusion_candidate")
            items[chunk] = item
            scores[chunk] = scores.get(chunk, 0.0) + 1.0 / (60 + rank)
    return [items[chunk] for chunk in sorted(items, key=lambda chunk: (-scores[chunk], chunk))]


def score(corpus: dict, review: dict, canary: dict, mapping: dict) -> dict:
    fingerprint = corpus["fingerprint"]
    if canonical_digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != fingerprint:
        raise ValueError("corpus_fingerprint_mismatch")
    if (review["source_corpus_fingerprint"] != fingerprint or canary["corpus_fingerprint"] != fingerprint
            or mapping["corpus_fingerprint"] != fingerprint):
        raise ValueError("corpus_binding_mismatch")
    if (canonical_digest({k: v for k, v in mapping.items() if k != "fingerprint"}) != mapping["fingerprint"]
            or canary["vector_mapping_fingerprint"] != mapping["fingerprint"]):
        raise ValueError("vector_mapping_mismatch")
    docs = {d["chunk_id"]: d for d in corpus["documents"]}
    rows = {r["chunk_id"]: r for r in mapping["rows"]}
    reviews = {r["case_id"]: r for r in review["cases"]}
    probes = {p["case_id"]: p for p in canary["probes"]}
    if len(rows) != len(mapping["rows"]) or len(reviews) != len(review["cases"]) or len(probes) != len(canary["probes"]):
        raise ValueError("duplicate_record")
    results = []
    for case in corpus["cases"]:
        label = reviews[case["case_id"]]
        probe = probes[case["case_id"]]
        if probe["question"] != case["question"] or [s["film_qid"] for s in probe["sides"]] != case["film_qids"]:
            raise ValueError("question_or_scope_mismatch")
        sides = []
        for side in probe["sides"]:
            qid = side["film_qid"]
            annotations = [e for e in label["evidence"] if e["film_qid"] == qid]
            for e in annotations:
                parent = docs[e["passage_id"]]
                if (parent["film_qid"] != qid or parent["content_sha256"] != e["content_sha256"]
                        or parent["content"][e["start"]:e["end"]] != e["quote"]):
                    raise ValueError("invalid_review_span")
            methods = {}
            rankings = {method: side["methods"][method]["evidence"] for method in ("semantic", "lexical")}
            rankings["semantic_section_reserve"] = reserve_sections(rankings["semantic"], case["question"])
            rankings["semantic_default_plot_reserve"] = reserve_sections(rankings["semantic"], case["question"], default_plot=True)
            rankings["hybrid_rrf60"] = reciprocal_rank_fusion(rankings["semantic"], rankings["lexical"])
            for method, ranked in rankings.items():
                for item in ranked:
                    row = rows[item["chunk_id"]]
                    parent = docs[row["passage_id"]]
                    if (parent["film_qid"] != qid or str(item["subject_entity_id"]) != row["entity_id"]
                            or str(item["source_snapshot_id"]) != row["snapshot_id"]
                            or hashlib.sha256(item["content"].encode("utf-8")).hexdigest() != row["chunk_sha256"]):
                        raise ValueError("candidate_source_mismatch")
                methods[method] = {str(k): sum(any(
                    rows[item["chunk_id"]]["passage_id"] == e["passage_id"] and e["quote"] in item["content"]
                    for item in ranked[:k]) for e in annotations) for k in (1, 5, 20)}
            sides.append({"film_qid": qid, "annotated_spans": len(annotations), "included": methods})
        results.append({"case_id": case["case_id"], "answerability": label["answerability"], "sides": sides})
    summary = {}
    for status in ("complete", "partial", "negative", "missing"):
        cases = [r for r in results if r["answerability"] == status]
        sides = [side for case in cases for side in case["sides"]]
        summary[status] = {"cases": len(cases), "annotated_spans": sum(s["annotated_spans"] for s in sides),
            "included": {method: {str(k): sum(s["included"][method][str(k)] for s in sides)
                for k in (1, 5, 20)} for method in ("semantic", "lexical", "semantic_section_reserve", "semantic_default_plot_reserve", "hybrid_rrf60")},
            "both_films_all_annotated_spans": {method: {str(k): sum(
                all(s["annotated_spans"] > 0 and s["included"][method][str(k)] == s["annotated_spans"]
                    for s in case["sides"]) for case in cases) for k in (1, 5, 20)}
                for method in ("semantic", "lexical", "semantic_section_reserve", "semantic_default_plot_reserve", "hybrid_rrf60")}}
    return {"schema": "cinegraph.recovery-pgvector-source-span-score/v1", "corpus_fingerprint": fingerprint,
        "mapping_fingerprint": mapping["fingerprint"], "canary_sha256": canonical_digest(canary),
        "review_sha256": canonical_digest(review), "summary": summary, "cases": results,
        "caution": "Single-reviewer development annotations, not answer accuracy or an independent quality score. The section-reserve policy was already inspected on these questions; the default-plot variant is a further development ablation. RRF uses only the retained top-20 inputs and is not necessarily the live hybrid policy. Exact quote inclusion may miss equivalent support or whitespace-normalized matches."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "review", "canary", "mapping", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "data" / "evaluation"
    if any(not p.resolve().is_relative_to(root) for p in vars(args).values()) or args.output.exists():
        raise ValueError("new_local_evaluation_output_required")
    result = score(*(json.loads(getattr(args, n).read_text()) for n in ("corpus", "review", "canary", "mapping")))
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
