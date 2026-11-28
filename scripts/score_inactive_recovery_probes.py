"""Source-bound span coverage for retained inactive-index development probes.

Labels are read only after retrieval has finished. This does not score answer
correctness, independent relevance, or writer usefulness.
"""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import EmbeddingIndexRun, EvidenceChunk
from app.services.corpus_build_manifest import canonical_digest
from score_recovery_pgvector_canary import reserve_sections


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probes",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    area=Path("data/evaluation").resolve()
    if any(not p.resolve().is_relative_to(area) for p in (args.probes,args.output)) or args.output.exists():
        raise ValueError("new_local_output_required")
    corpus=json.loads((area/"recovery-ten-film-current-v1.json").read_text())
    review=json.loads((area/"recovery-oracle-review-development-complete-v1.json").read_text())
    probes=json.loads(args.probes.read_text())
    if (not probes["development"] or review["source_corpus_fingerprint"]!=corpus["fingerprint"]
            or probes["corpus_fingerprint"]!=corpus["fingerprint"]
            or canonical_digest({k:v for k,v in corpus.items() if k!="fingerprint"})!=corpus["fingerprint"]):
        raise ValueError("development_corpus_binding_mismatch")
    if [c["case_id"] for c in probes["probes"]]!=[c["case_id"] for c in corpus["cases"]]:
        raise ValueError("incomplete_development_packet")
    parents={d["chunk_id"]:d for d in corpus["documents"]}
    labels={c["case_id"]:c for c in review["cases"]}
    results=[]
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        index=db.get(EmbeddingIndexRun,UUID(probes["index_run_id"]))
        chunks={str(c.id):c for c in db.scalars(select(EvidenceChunk).where(
            EvidenceChunk.preprocessing_run_id==index.evidence_chunk_run_id))}
        for probe,case in zip(probes["probes"],corpus["cases"],strict=True):
            if probe["question"]!=case["question"] or [s["qid"] for s in probe["sides"]]!=case["film_qids"]:
                raise ValueError("question_scope_mismatch")
            label=labels[case["case_id"]]
            sides=[]
            for side in probe["sides"]:
                spans=[e for e in label["evidence"] if e["film_qid"]==side["qid"]]
                for span in spans:
                    parent=parents[span["passage_id"]]
                    if (parent["film_qid"]!=side["qid"] or parent["content_sha256"]!=span["content_sha256"]
                            or parent["source_snapshot_id"]!=span["source_snapshot_id"]
                            or parent["source_revision"]!=span["source_revision"]
                            or parent["content"][span["start"]:span["end"]]!=span["quote"]):
                        raise ValueError("invalid_annotation_span")
                ranks={name:r["evidence"] for name,r in side["methods"].items()}
                ranks["semantic_section_reserve"]=reserve_sections(ranks["semantic"],case["question"])
                counts={}
                for name,items in ranks.items():
                    for item in items:
                        chunk=chunks[item["chunk_id"]]
                        parent=parents[str(chunk.narrative_passage_id)]
                        if (parent["film_qid"]!=side["qid"] or item["content"]!=chunk.content
                                or item["subject_entity_id"]!=str(chunk.subject_entity_id)
                                or item["source_snapshot_id"]!=str(chunk.source_snapshot_id)
                                or hashlib.sha256(item["content"].encode()).hexdigest()!=chunk.content_hash):
                            raise ValueError("ranked_source_mismatch")
                    counts[name]={str(k):sum(any(str(chunks[item["chunk_id"]].narrative_passage_id)==s["passage_id"]
                        and s["quote"] in item["content"] for item in items[:k]) for s in spans) for k in (5,20)}
                sides.append({"qid":side["qid"],"spans":len(spans),"included":counts})
            results.append({"case_id":case["case_id"],"answerability":label["answerability"],"sides":sides})
    complete=[r for r in results if r["answerability"]=="complete"]
    summary={name:{str(k):sum(all(s["spans"]>0 and s["included"][name][str(k)]==s["spans"]
        for s in r["sides"]) for r in complete) for k in (5,20)} for name in results[0]["sides"][0]["included"]}
    report={"complete_cases":len(complete),"both_films_all_annotated_spans":summary,"cases":results,
        "probes_sha256":canonical_digest(probes),"review_sha256":canonical_digest(review),
        "caution":"Single-reviewer development span inclusion; not answer accuracy or release evidence."}
    with args.output.open("x") as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps({"complete_cases":len(complete),"both_films_all_annotated_spans":summary}))


if __name__=="__main__":
    main()
