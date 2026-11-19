"""Repack one retained diagnostic ranking; no model, DB, or source writes."""
import argparse
import json
from pathlib import Path
from app.services.corpus_build_manifest import canonical_digest
from app.services.evidence_facet_selection import select_evidence_leads


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--ranking", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-narrative-lead", action="store_true")
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    corpus = json.loads(args.corpus.read_text())
    fingerprint = corpus.pop("fingerprint")
    if canonical_digest(corpus) != fingerprint:
        raise ValueError("corpus_fingerprint_mismatch")
    ranking = json.loads(args.ranking.read_text())
    if ranking["contract"]["corpus"] != fingerprint:
        raise ValueError("ranking_corpus_mismatch")
    parents = {d["chunk_id"]: d for d in corpus["documents"]}
    result = {"corpus": fingerprint, "ranking_contract": ranking["contract"],
              "facet_requested_by_operator": args.require_narrative_lead,
              "quality_score": None, "cases": []}
    for case in ranking["cases"]:
        result["cases"].append({"case_id": case["case_id"], "question": case["question"],
            "sides": [{"film_qid": side["film_qid"], **select_evidence_leads(
                side["ranked"], parents, film_qid=side["film_qid"],
                require_narrative_lead=args.require_narrative_lead)} for side in case["sides"]]})
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps([{"case": c["case_id"], "sides": [
        {"film": s["film_qid"], "selected_dense_ranks": [r["dense_rank"] for r in s["selected"]],
         "missing": s["missing_facets"]} for s in c["sides"]]} for c in result["cases"]]))


if __name__ == "__main__":
    main()
