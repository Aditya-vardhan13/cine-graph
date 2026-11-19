"""Bind manual source-support observations to exact frozen passage spans."""
import argparse
import hashlib
import json
from pathlib import Path
from app.services.corpus_build_manifest import canonical_digest


def bind_review(corpus, annotations):
    payload = {k:v for k,v in corpus.items() if k != "fingerprint"}
    if canonical_digest(payload) != corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    documents = {d["chunk_id"]:d for d in corpus["documents"]}
    cases = {c["case_id"]:c for c in corpus["cases"]}
    output, seen = [], set()
    for annotation in annotations:
        cid = annotation["case_id"]
        if cid not in cases or cid in seen:
            raise ValueError("invalid_or_duplicate_case")
        seen.add(cid)
        if annotation["answerability"] not in {"complete", "partial", "missing", "negative"}:
            raise ValueError("unknown_answerability")
        evidence = []
        for item in annotation["evidence"]:
            doc = documents[item["passage_id"]]
            if doc["film_qid"] not in cases[cid]["film_qids"]:
                raise ValueError("wrong_film_evidence")
            if hashlib.sha256(doc["content"].encode()).hexdigest() != doc["content_sha256"]:
                raise ValueError("passage_hash_mismatch")
            quote = item["quote"]
            if not quote or doc["content"].count(quote) != 1:
                raise ValueError("quote_missing_or_not_unique")
            start = doc["content"].index(quote)
            evidence.append({**item,"film_qid":doc["film_qid"],"start":start,
                "end":start+len(quote),"source_snapshot_id":doc["source_snapshot_id"],
                "source_revision":doc["source_revision"],"content_sha256":doc["content_sha256"]})
        if annotation["answerability"] in {"complete","partial"} and (
            {e["film_qid"] for e in evidence} != set(cases[cid]["film_qids"])):
            raise ValueError("both_films_need_source_review")
        output.append({**annotation,"evidence":evidence})
    return {"schema":"cinegraph.source-oracle-review/v1",
        "source_corpus_fingerprint":corpus["fingerprint"],
        "reviewer":"codex-single-source-aware-reviewer",
        "independently_adjudicated":False,"release_gold":False,
        "caution":"Exact spans prove source binding, not annotation correctness or independent film truth.",
        "cases":output}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("corpus","annotations","output"):
        p.add_argument("--"+key,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result=bind_review(json.loads(args.corpus.read_text()),json.loads(args.annotations.read_text()))
    with args.output.open("x") as h:
        json.dump(result,h,ensure_ascii=False,indent=2)
        h.write("\n")
    print(json.dumps({"reviewed_cases":len(result["cases"]),"release_gold":False}))


if __name__=="__main__":
    main()
