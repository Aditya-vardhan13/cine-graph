"""Find exact quote locations in a new corpus without migrating review labels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.rag_dense_trial import digest
from app.services.rag_span_review import bind_review_quotes


def audit_rebinding(old: dict, new: dict, authored_review: dict) -> dict:
    review = bind_review_quotes(old, authored_review)
    if digest({k: v for k, v in new.items() if k != "fingerprint"}) != new.get("fingerprint"):
        raise ValueError("Target corpus fingerprint failed.")
    old_cases = {case["case_id"]: case for case in old["cases"]}
    new_cases = {case["case_id"]: case for case in new["cases"]}
    if old_cases != new_cases:
        raise ValueError("Both corpora must use the exact same frozen questions and film identities.")
    documents = {row["chunk_id"]: row for row in old["documents"]}
    results = []
    for case in review["cases"]:
        for evidence in case["evidence"]:
            original = documents[evidence["chunk_id"]]
            candidates = []
            for target in new["documents"]:
                if (target["film_qid"] != evidence["film_qid"] or
                        target["source_snapshot_id"] != original["source_snapshot_id"]):
                    continue
                offset = 0
                while (start := target["content"].find(evidence["quote"], offset)) >= 0:
                    candidates.append({"chunk_id": target["chunk_id"], "start": start,
                                       "end": start + len(evidence["quote"])})
                    offset = start + 1
            results.append({"case_id": case["case_id"], "film_qid": evidence["film_qid"],
                            "original_chunk_id": evidence["chunk_id"], "candidates": candidates,
                            "status": "unique" if len(candidates) == 1 else "missing" if not candidates else "ambiguous"})
    return {"version": "source-rebinding-audit-v1", "source_corpus": old["fingerprint"],
            "target_corpus": new["fingerprint"], "review_fingerprint": digest(authored_review),
            "status": "candidate-locations-only-not-reviewed-labels", "items": results,
            "summary": {name: sum(row["status"] == name for row in results)
                        for name in ("unique", "missing", "ambiguous")},
            "caution": "An exact quote match does not validate its interpretation, completeness, or entailment."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    if any(not p.resolve().is_relative_to(root) for p in (args.source, args.target, args.review, args.output)):
        raise ValueError("Source content and audits must stay in local evaluation storage.")
    result = audit_rebinding(*(json.loads(p.read_text()) for p in (args.source, args.target, args.review)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({"status": result["status"], "summary": result["summary"]}))


if __name__ == "__main__":
    main()
