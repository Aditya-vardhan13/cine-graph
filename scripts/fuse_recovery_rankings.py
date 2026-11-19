"""Offline full-parent RRF control using retained dense results, without inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.corpus_build_manifest import canonical_digest
from app.services.lexical_retrieval import Bm25Index, weighted_reciprocal_rank_fusion


def fuse(corpus, dense, *, dense_weight=3, lexical_weight=1, depth=10):
    if depth < 1:
        raise ValueError("positive_depth_required")
    if canonical_digest({k:v for k,v in corpus.items() if k!="fingerprint"})!=corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    if dense["contract"]["corpus"]!=corpus["fingerprint"]:
        raise ValueError("ranking_corpus_mismatch")
    if dense["contract"]["representation"]!="source-full-parent-v1":
        raise ValueError("full_parent_control_required")
    if [c["case_id"] for c in dense["cases"]]!=[c["case_id"] for c in corpus["cases"]]:
        raise ValueError("ranking_case_sequence_mismatch")
    documents={d["chunk_id"]:d for d in corpus["documents"]}
    cases=[]
    for case,row in zip(corpus["cases"],dense["cases"],strict=True):
        if row["question"]!=case["question"] or [s["film_qid"] for s in row["sides"]]!=case["film_qids"]:
            raise ValueError("ranking_question_or_film_mismatch")
        sides=[]
        for side in row["sides"]:
            docs=[d for d in corpus["documents"] if d["film_qid"]==side["film_qid"]]
            dense_ids=[]
            for item in side["ranked"]:
                doc=documents[item["chunk_id"]]
                if (doc["film_qid"]!=side["film_qid"] or item["text"]!=doc["content"]
                    or item["start"]!=0 or item["end"]!=len(doc["content"])):
                    raise ValueError("ranking_source_span_mismatch")
                dense_ids.append(item["chunk_id"])
            if len(dense_ids)!=len(set(dense_ids)):
                raise ValueError("duplicate_dense_parent")
            lexical=Bm25Index.build(d["section_title"]+" "+d["content"] for d in docs)
            lexical_ids=[docs[i]["chunk_id"] for i in lexical.rank(case["question"],cutoff=depth)]
            ids=weighted_reciprocal_rank_fusion(
                [(dense_ids[:depth],dense_weight),(lexical_ids,lexical_weight)],cutoff=depth)
            ranked=[]
            for identifier in ids:
                doc=documents[identifier]
                score=sum(weight/(60+lane.index(identifier)+1) for lane,weight in
                    ((dense_ids[:depth],dense_weight),(lexical_ids,lexical_weight)) if identifier in lane)
                ranked.append({"chunk_id":identifier,"film_qid":doc["film_qid"],
                    "start":0,"end":len(doc["content"]),"text":doc["content"],"score":score})
            sides.append({"film_qid":side["film_qid"],"ranked":ranked})
        cases.append({"case_id":case["case_id"],"question":case["question"],"sides":sides})
    return {"contract":{**dense["contract"],"fusion":"weighted-rrf-k60",
        "dense_weight":dense_weight,"lexical_weight":lexical_weight,"lane_depth":depth,
        "retained_dense_sha256":canonical_digest(dense)},"cases":cases}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("corpus","dense","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    result=fuse(json.loads(args.corpus.read_text()),json.loads(args.dense.read_text()))
    with args.output.open("x") as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2)
        handle.write("\n")


if __name__=="__main__":
    main()
