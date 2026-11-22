"""Bind a frozen pilot export to retained current snapshots, read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from app.db import SessionLocal
from app.models import SourceObject
from app.services.corpus_build_manifest import canonical_digest
from app.services.current_narrative_passages import current_passage_rows
from app.services.narrative_use_decisions import latest_decisions
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.source_rights_policy import can_use_narrative_semantically


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1] / "data" / "evaluation"
    if not all(x.resolve().is_relative_to(root) for x in (args.corpus, args.output)) or args.output.exists():
        raise ValueError("new_local_evaluation_output_required")
    corpus = json.loads(args.corpus.read_text())
    fingerprint = corpus["fingerprint"]
    if canonical_digest({k:v for k,v in corpus.items() if k != "fingerprint"}) != fingerprint:
        raise ValueError("corpus_fingerprint_mismatch")
    docs = corpus["documents"]
    if len({d["chunk_id"] for d in docs}) != len(docs):
        raise ValueError("duplicate_passage_id")
    entities = {UUID(d["entity_id"]) for d in docs}
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        current = {str(p.id):(p,s) for p,s in current_passage_rows(db, entities)}
        snapshots = {}
        for d in docs:
            row = current.get(d["chunk_id"])
            if row is None:
                raise ValueError("frozen_passage_not_current")
            passage,snapshot = row
            if (str(passage.subject_entity_id) != d["entity_id"] or str(snapshot.id) != d["source_snapshot_id"]
                or passage.content != d["content"] or passage.content_hash != d["content_sha256"]
                or hashlib.sha256(passage.content.encode()).hexdigest() != passage.content_hash
                or passage.section_locator != d["section_locator"] or passage.section_title != d["section_title"]
                or passage.ordinal != d["passage_ordinal"] or passage.extraction_version != d["extraction_version"]
                or snapshot.content_hash != d["source_sha256"] or snapshot.source_revision != d["source_revision"]
                or snapshot.canonical_url != d["source_url"] or snapshot.license != d["source_license"]
                or snapshot.attribution_url != d["attribution_url"]):
                raise ValueError("frozen_passage_source_mismatch")
            snapshots[snapshot.id] = snapshot
        decisions = latest_decisions(db, set(snapshots))
        if any(not decisions.get(UUID(d["source_snapshot_id"])) or
               decisions[UUID(d["source_snapshot_id"])].decision_version != d["decision_version"] for d in docs):
            raise ValueError("frozen_decision_version_changed")
        result_sources = []
        for sid,s in sorted(snapshots.items(), key=lambda row: str(row[0])):
            d = decisions.get(sid)
            if (s.fetch_status != "success" or not d or not can_use_narrative_semantically(
                decision=d.decision, basis_url=d.decision_basis_url, notes=d.decision_notes,
                license_name=s.license, attribution_url=s.attribution_url)
                or verify_snapshot_file(s.storage_uri,s.content_hash,s.byte_size) != "verified"):
                raise ValueError("snapshot_not_currently_eligible_or_verified")
            obj = db.scalar(select(SourceObject).where(SourceObject.id == s.source_object_id))
            if obj is None:
                raise ValueError("snapshot_object_missing")
            result_sources.append({"snapshot_id":str(sid),"object_id":str(obj.id),"external_id":obj.external_id,
                "object_kind":obj.object_kind,"canonical_url":s.canonical_url,"source_revision":s.source_revision,
                "retrieved_at":s.retrieved_at.isoformat(),"content_hash":s.content_hash,"byte_size":s.byte_size,
                "storage_uri":s.storage_uri,"license":s.license,"attribution_url":s.attribution_url,
                "parser_version":s.parser_version,"decision_version":d.decision_version,
                "decision_basis_url":d.decision_basis_url,"decision_notes":d.decision_notes,"reviewer":d.reviewer})
    result = {"schema":"cinegraph.recovery-pilot-descriptors/v1","corpus_fingerprint":fingerprint,
        "sources":result_sources,"note":"Local research replay only; not a new rights approval."}
    result["fingerprint"] = canonical_digest(result)
    with args.output.open("x") as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2); handle.write("\n")
    print(json.dumps({"films":len(entities),"passages":len(docs),"snapshots":len(result_sources),"fingerprint":result["fingerprint"]}))


if __name__ == "__main__":
    main()
