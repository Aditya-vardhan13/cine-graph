"""Bind a completed reranker checkpoint to frozen source parents for scoring."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from app.services.corpus_build_manifest import canonical_digest


def convert(corpus, capture, result):
    if canonical_digest({k:v for k,v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    if capture["corpus_fingerprint"] != corpus["fingerprint"]:
        raise ValueError("capture_corpus_mismatch")
    fingerprint=hashlib.sha256(json.dumps(capture,sort_keys=True).encode()).hexdigest()
    if result["capture_fingerprint"] != fingerprint or not result["complete"]:
        raise ValueError("incomplete_or_mismatched_checkpoint")
    if ([x["case_id"] for x in result["cases"]] != [x["case_id"] for x in capture["cases"]]
        or [x["case_id"] for x in capture["cases"]] != [x["case_id"] for x in corpus["cases"]]):
        raise ValueError("case_sequence_mismatch")
    docs={x["chunk_id"]:x for x in corpus["documents"]}
    cases=[]
    for source, frozen, ranked in zip(corpus["cases"],capture["cases"],result["cases"],strict=True):
        if (source["question"] != frozen["question"] or source["question"] != ranked["question"]
            or source["film_qids"] != frozen["film_qids"] or source["film_qids"] != ranked["film_qids"]):
            raise ValueError("question_or_film_mismatch")
        sides=[]
        for name,qid in zip(("first","second"),source["film_qids"],strict=True):
            pool=frozen[f"{name}_pool"]
            ranking=ranked[f"{name}_ranking"]
            pool_ids=[x["chunk_id"] for x in pool]
            rank_ids=[x["chunk_id"] for x in ranking]
            if len(pool_ids)!=len(set(pool_ids)) or len(rank_ids)!=len(set(rank_ids)) or set(rank_ids)!=set(pool_ids):
                raise ValueError("ranking_candidate_set_mismatch")
            by_id={x["chunk_id"]:x for x in pool}
            output=[]
            for item in ranking:
                doc=docs[item["chunk_id"]]
                candidate=by_id[item["chunk_id"]]
                if (doc["film_qid"]!=qid or candidate["content"]!=doc["content"]
                    or candidate["source_snapshot_id"]!=doc["source_snapshot_id"]
                    or not math.isfinite(item["score"])):
                    raise ValueError("candidate_source_mismatch")
                output.append({"chunk_id":doc["chunk_id"],"film_qid":qid,"score":item["score"],
                    "start":0,"end":len(doc["content"]),"text":doc["content"]})
            sides.append({"film_qid":qid,"ranked":output})
        cases.append({"case_id":source["case_id"],"question":source["question"],"sides":sides})
    return {"contract":{"corpus":corpus["fingerprint"],"representation":"source-full-parent-v1",
        "reranker_model":result["model"],"instruction":result["instruction"],
        "capture_fingerprint":fingerprint,"checkpoint_sha256":canonical_digest(result)},"cases":cases}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("corpus","capture","result","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    converted=convert(*(json.loads(getattr(args,k).read_text()) for k in ("corpus","capture","result")))
    with args.output.open("x") as handle:
        json.dump(converted,handle,ensure_ascii=False,indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
