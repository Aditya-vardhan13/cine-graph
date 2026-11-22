"""Offline question-only section-reserve ablation over a retained ranking.

No labels, model inference, source writes, or live retrieval changes are used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from app.services.corpus_build_manifest import canonical_digest


def requested_section(question: str) -> str | None:
    """Conservative, explicitly limited question-text routing hypothesis."""
    q = question.casefold()
    if re.search(r"\b(critics?|reviews?|reviewers?|reception|audiences?|criticism)\b", q):
        return "reception"
    if re.search(r"\b(filmmakers?|directors?|cinematography|camera|editing|screenplay|production|craft)\b", q):
        return "production"
    if re.search(r"\b(actions?|choices?|chooses?|decisions?|characters?|risks?|relationships?|consequences?)\b", q):
        return "plot"
    return None


def reserve(ranked: list[dict], parents: dict[str, dict], film_qid: str, section: str | None) -> list[dict]:
    if len({r["chunk_id"] for r in ranked}) != len(ranked):
        raise ValueError("duplicate_ranked_parent")
    for row in ranked:
        parent = parents.get(row["chunk_id"])
        if parent is None or parent["film_qid"] != film_qid or row["film_qid"] != film_qid:
            raise ValueError("candidate_outside_film")
    if section is None:
        return list(ranked)
    def matches(row):
        return parents[row["chunk_id"]]["section_title"].split("/")[0].strip().casefold() == section
    selected = list(ranked[:5])
    for candidate in ranked[5:]:
        if sum(matches(row) for row in selected) >= 2:
            break
        if not matches(candidate):
            continue
        replace = next((i for i in range(len(selected)-1, -1, -1) if not matches(selected[i])), None)
        if replace is None:
            break
        selected[replace] = candidate
    selected_ids = {row["chunk_id"] for row in selected}
    return selected + [row for row in ranked if row["chunk_id"] not in selected_ids]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--ranking", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]/"data"/"evaluation"
    if any(not path.resolve().is_relative_to(root) for path in (a.corpus,a.ranking,a.output)) or a.output.exists():
        raise ValueError("new_local_evaluation_output_required")
    corpus=json.loads(a.corpus.read_text())
    if canonical_digest({k:v for k,v in corpus.items() if k!="fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    ranking=json.loads(a.ranking.read_text())
    ranking_fingerprint=canonical_digest(ranking)
    if ranking["contract"]["corpus"] != corpus["fingerprint"]:
        raise ValueError("ranking_corpus_mismatch")
    if [c["case_id"] for c in ranking["cases"]] != [c["case_id"] for c in corpus["cases"]]:
        raise ValueError("ranking_case_mismatch")
    parents={d["chunk_id"]:d for d in corpus["documents"]}
    route_counts={}
    for case,source in zip(ranking["cases"],corpus["cases"],strict=True):
        if case["question"] != source["question"] or [s["film_qid"] for s in case["sides"]] != source["film_qids"]:
            raise ValueError("question_or_scope_mismatch")
        section=requested_section(case["question"])
        route_counts[section or "none"]=route_counts.get(section or "none",0)+1
        for side in case["sides"]:
            side["ranked"]=reserve(side["ranked"],parents,side["film_qid"],section)
    ranking["selection_policy"]="question-only-section-reserve-two-v1"
    ranking["input_ranking_sha256"]=ranking_fingerprint
    ranking["route_counts"]=route_counts
    with a.output.open("x") as h:
        json.dump(ranking,h,ensure_ascii=False,indent=2); h.write("\n")
    print(json.dumps(route_counts))


if __name__ == "__main__":
    main()
