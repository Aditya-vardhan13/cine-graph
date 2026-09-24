"""Materialize new passage provenance after pinned revisions pass recovery audit.

This is an explicit, resumable manual job. It never repoints historical
passages or promotes narrative text to operational facts.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NarrativePassage, SourceAssertion, SourceSnapshot
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikipedia_recovery_audit import recovery_matches_original
from app.services.wikipedia_research import extract_passages
from app.services.wikipedia_revision_recovery import ADAPTER_VERSION


def recovered_qid(db: Session, recovered: SourceSnapshot) -> str | None:
    qids = set(db.scalars(
        select(SourceAssertion.raw_value["wikidata_id"].as_string())
        .join(SourceSnapshot, SourceSnapshot.id == SourceAssertion.source_snapshot_id)
        .where(
            SourceSnapshot.source_object_id == recovered.source_object_id,
            SourceSnapshot.source_revision == recovered.source_revision,
            SourceAssertion.source_property == "wikidata_item",
        )
    ))
    qids.discard(None)
    return next(iter(qids)) if len(qids) == 1 else None


def materialize_recovered_passages(db: Session, *, limit: int | None = None, execute: bool = False) -> dict:
    snapshots = db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.parser_version == ADAPTER_VERSION,
    ).order_by(SourceSnapshot.retrieved_at)).all()
    materialized_ids = set(db.scalars(select(NarrativePassage.source_snapshot_id).distinct().where(
        NarrativePassage.source_snapshot_id.in_([snapshot.id for snapshot in snapshots]),
    )))
    pending: list[tuple[SourceSnapshot, str]] = []
    unresolved = 0
    for snapshot in snapshots:
        if snapshot.id in materialized_ids:
            continue
        if verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified":
            unresolved += 1
            continue
        qid = recovered_qid(db, snapshot)
        if not qid or not recovery_matches_original(db, snapshot):
            unresolved += 1
            continue
        pending.append((snapshot, qid))
    selected = pending[:limit] if limit is not None else pending
    report = {
        "recovered_snapshots": len(snapshots), "already_materialized": len(materialized_ids),
        "eligible": len(pending),
        "unresolved": unresolved, "selected": len(selected),
        "processed": 0, "passages_created": 0, "status": "dry_run",
    }
    if not execute:
        return report
    for snapshot, qid in selected:
        result = extract_passages(db, qid, recovered_snapshot_id=snapshot.id)
        report["processed"] += 1
        report["passages_created"] += result["passages_created"]
    report["status"] = "complete"
    return report


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Explicitly extract versioned passages from recovered Wikipedia snapshots.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    with SessionLocal() as db:
        report = materialize_recovered_passages(db, limit=args.limit, execute=args.execute)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
