"""Offline BM25 reference; source-span inclusion is not writer-answer accuracy."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import time
from app.services.corpus_build_manifest import canonical_digest
from app.services.lexical_retrieval import Bm25Index


def evaluate(corpus, review, cutoff=5, retained_ranking=None):
    if cutoff < 1:
        raise ValueError("positive_cutoff_required")
    if canonical_digest({k:v for k,v in corpus.items() if k!="fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    if review["source_corpus_fingerprint"] != corpus["fingerprint"]:
        raise ValueError("review_corpus_mismatch")
    documents = {d["chunk_id"]:d for d in corpus["documents"]}
    labels = {r["case_id"]:r for r in review["cases"]}
    if len(labels) != len(review["cases"]):
        raise ValueError("duplicate_review_case")
    if set(labels) != {c["case_id"] for c in corpus["cases"]}:
        raise ValueError("exact_case_coverage_required")
    cutoffs=(cutoff,) if retained_ranking is not None else (cutoff,20)
    retained={}
    if retained_ranking is not None:
        if retained_ranking["contract"]["corpus"]!=corpus["fingerprint"]:
            raise ValueError("ranking_corpus_mismatch")
        rows=retained_ranking["cases"]
        if [r["case_id"] for r in rows]!=[c["case_id"] for c in corpus["cases"]]:
            raise ValueError("ranking_case_sequence_mismatch")
        for case,row in zip(corpus["cases"],rows,strict=True):
            if row["question"]!=case["question"] or [s["film_qid"] for s in row["sides"]]!=case["film_qids"]:
                raise ValueError("ranking_question_or_film_mismatch")
            for side in row["sides"]:
                for item in side["ranked"]:
                    doc=documents.get(item["chunk_id"])
                    if (doc is None or doc["film_qid"]!=side["film_qid"]
                        or item.get("film_qid")!=side["film_qid"]
                        or not math.isfinite(item["score"])):
                        raise ValueError("ranking_invalid_candidate")
                    start,end=item.get("start",0),item.get("end",len(doc["content"]))
                    if not 0<=start<end<=len(doc["content"]) or item.get("text",doc["content"][start:end])!=doc["content"][start:end]:
                        raise ValueError("ranking_source_span_mismatch")
                retained[(case["case_id"],side["film_qid"])]=side["ranked"]
    grouped = defaultdict(list)
    for doc in corpus["documents"]:
        grouped[doc["film_qid"]].append(doc)
    indexes = {qid:Bm25Index.build(d["section_title"]+" "+d["content"] for d in docs)
               for qid,docs in grouped.items()}
    results=[]
    for case in corpus["cases"]:
        annotation=labels[case["case_id"]]
        sides=[]
        for qid in case["film_qids"]:
            start=time.monotonic()
            docs=grouped[qid]
            scores=indexes[qid].scores(case["question"])
            order=sorted(range(len(docs)),key=lambda i:(-scores[i],docs[i]["chunk_id"]))
            ranked=[{"chunk_id":docs[i]["chunk_id"],"score":scores[i]} for i in order[:20]]
            if retained_ranking is not None:
                ranked=retained[(case["case_id"],qid)]
            evidence=[e for e in annotation["evidence"] if e["film_qid"]==qid]
            for e in evidence:
                doc=documents[e["passage_id"]]
                if (doc["film_qid"]!=qid or doc["content"][e["start"]:e["end"]]!=e["quote"]
                    or doc["content_sha256"]!=e["content_sha256"]):
                    raise ValueError("invalid_review_span")
            counts={str(k):sum(any(
                r["chunk_id"]==e["passage_id"] and r.get("start",0)<=e["start"]
                and r.get("end",len(documents[r["chunk_id"]]["content"]))>=e["end"]
                for r in ranked[:k]) for e in evidence) for k in cutoffs}
            sides.append({"film_qid":qid,"ranked":ranked,"annotated_spans":len(evidence),
                "included_annotated_spans":counts,"ranking_seconds":time.monotonic()-start})
        results.append({"case_id":case["case_id"],"question":case["question"],
                        "answerability":annotation["answerability"],"sides":sides})
    summary={}
    for status in ("complete","partial","negative","missing"):
        rows=[s for c in results if c["answerability"]==status for s in c["sides"]]
        summary[status]={"cases":sum(c["answerability"]==status for c in results),
            "annotated_spans":sum(r["annotated_spans"] for r in rows),
            "included_annotated_spans":{str(k):sum(r["included_annotated_spans"][str(k)] for r in rows)
                                      for k in cutoffs}}
    return {"schema":"cinegraph.recovery-source-span-inclusion/v2",
        "source_corpus_fingerprint":corpus["fingerprint"],
        "review_sha256":canonical_digest(review),"cutoff":cutoff,
        "representation":retained_ranking["contract"]["representation"] if retained_ranking is not None else "section-and-full-retained-parent",
        "ranker_contract":retained_ranking["contract"] if retained_ranking is not None else {"method":"bm25"},
        "independent_gold":False,"answer_accuracy":None,
        "caution":"Inclusion of complete manually annotated spans within retained retrieval windows. Alternative supporting passages may be unlabelled; annotations may be incomplete or wrong. No entailment, abstention or writer usefulness score. Retained ranking timing is not inference latency.",
        "summary":summary,"cases":results}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("corpus","review","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--ranking",type=Path)
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result=evaluate(json.loads(args.corpus.read_text()),json.loads(args.review.read_text()),
                    retained_ranking=json.loads(args.ranking.read_text()) if args.ranking else None)
    with args.output.open("x") as h:
        json.dump(result,h,ensure_ascii=False,indent=2)
        h.write("\n")
    print(json.dumps(result["summary"]))


if __name__=="__main__":
    main()
