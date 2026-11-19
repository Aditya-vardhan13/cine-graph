"""Read-only identity proposals from local IMDb lookup and retained reviewed cross-IDs.

Never chooses a fuzzy match or writes an operational fact. Output remains local.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import Assertion, CanonicalEntity
from app.services.corpus_build_manifest import canonical_digest
from app.services.imdb_dataset import ImdbDataset


def propose(rows, searches, cross_ids):
    by_id=defaultdict(list)
    for row in cross_ids:
        by_id[row["imdb_id"]].append(row)
    results=[]
    for row in rows:
        candidates=[]
        for item in searches[row["target_rank"]]:
            candidates.append({**item,"retained_cross_ids":by_id.get(item["tconst"],[]),
                "year_delta":item["year"]-row["year_candidate"] if item["year"] is not None else None})
        results.append({"target_rank":row["target_rank"],"title":row["title"],
            "year_candidate":row["year_candidate"],"candidates":candidates,
            "identity_review":"required","identity_approved":False})
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation",type=Path,required=True)
    parser.add_argument("--data-dir",type=Path,default=Path("imdb_data"))
    parser.add_argument("--index-dir",type=Path,default=Path("data/imdb_index"))
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/"data"/"reports"):
        raise ValueError("Review output must stay in local data/reports")
    if args.output.exists():
        raise FileExistsError(args.output)
    original=json.loads(args.reconciliation.read_text())
    if canonical_digest({k:v for k,v in original.items() if k!="report_sha256"})!=original["report_sha256"]:
        raise ValueError("reconciliation_fingerprint_mismatch")
    rows=[r for r in original["rows"] if r["status"]!="current_candidate"]
    dataset=ImdbDataset(args.data_dir,args.index_dir)
    # Validate basics TSV/index stat contract even though discovery uses the
    # small derived title lookup. Hash lineage remains a source/index claim,
    # not a new rehash of all IMDb dumps on every diagnostic run.
    basics=dataset._index("basics")
    searches={r["target_rank"]:dataset.search_title(r["title"],r["year_candidate"],limit=4) for r in rows}
    cross_ids=[]
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        for assertion,entity in db.execute(select(Assertion,CanonicalEntity).join(
            CanonicalEntity,CanonicalEntity.id==Assertion.subject_entity_id).where(
                Assertion.predicate=="imdb_identifier",
                Assertion.review_status.in_(("resolved","published")),
                CanonicalEntity.entity_kind=="film",CanonicalEntity.lifecycle_status=="active")):
            identifier=(assertion.value_json or {}).get("value")
            if identifier:
                cross_ids.append({"imdb_id":identifier,"assertion_id":str(assertion.id),
                    "entity_id":str(entity.id),"wikidata_id":entity.wikidata_id,
                    "title":entity.canonical_label,"review_status":assertion.review_status})
        db.rollback()
    result={"schema":"cinegraph.recovery-identity-proposals/v1",
        "reconciliation_sha256":original["report_sha256"],"imdb_basics_sha256":basics["sha256"],
        "note":"Fuzzy proposals and retained cross-IDs only; no identity approvals, source recapture or canonical writes.",
        "rows":propose(rows,searches,cross_ids)}
    result["report_sha256"]=canonical_digest(result)
    with args.output.open("x") as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2); handle.write("\n")
    print(json.dumps({"rows":len(rows),"with_candidates":sum(bool(r["candidates"]) for r in result["rows"]),
        "with_retained_cross_ids":sum(any(c["retained_cross_ids"] for c in r["candidates"]) for r in result["rows"])}))


if __name__=="__main__":
    main()
