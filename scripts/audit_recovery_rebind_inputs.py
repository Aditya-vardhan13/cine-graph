"""Read-only preflight for rebinding retained pilot vectors to current sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from app.db import SessionLocal
from app.services.corpus_build_manifest import canonical_digest
from app.services.current_narrative_passages import current_passage_rows
from app.services.narrative_use_decisions import latest_decisions
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.source_rights_policy import can_use_narrative_semantically


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    args = parser.parse_args()
    area = (Path.cwd() / "data" / "evaluation").resolve()
    if not args.corpus.resolve().is_relative_to(area):
        raise ValueError("local_pilot_corpus_required")
    corpus = json.loads(args.corpus.read_text())
    if canonical_digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    docs = corpus["documents"]
    expected = {(d["entity_id"], d["source_snapshot_id"], d["chunk_id"], d["content_sha256"]) for d in docs}
    entities = {UUID(d["entity_id"]) for d in docs}
    if len(expected) != len(docs) or len(entities) != 10:
        raise ValueError("unexpected_pilot_scope")
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        rows = current_passage_rows(db, entities)
        decisions = latest_decisions(db, {snapshot.id for _, snapshot in rows})
        verified = {}
        actual = set()
        for passage, snapshot in rows:
            decision = decisions.get(snapshot.id)
            if not can_use_narrative_semantically(
                decision=decision.decision if decision else None,
                basis_url=decision.decision_basis_url if decision else None,
                notes=decision.decision_notes if decision else None,
                license_name=snapshot.license, attribution_url=snapshot.attribution_url,
            ) or snapshot.fetch_status != "success":
                continue
            if snapshot.id not in verified:
                verified[snapshot.id] = verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size)
            if verified[snapshot.id] != "verified" or hashlib.sha256(passage.content.encode("utf-8")).hexdigest() != passage.content_hash:
                raise ValueError("current_source_integrity_failed")
            actual.add((str(passage.subject_entity_id), str(snapshot.id), str(passage.id), passage.content_hash))
        print(json.dumps({"schema": "cinegraph.rebind-current-input-audit/v1", "corpus_fingerprint": corpus["fingerprint"],
            "films": len(entities), "retained_passages": len(expected), "current_eligible_passages": len(actual),
            "missing_from_current": len(expected - actual), "additional_current": len(actual - expected),
            "snapshots_checked": len(verified), "source_match": expected == actual,
            "caution": "Read-only source preflight only; not identity approval, retrieval quality, or activation permission."}))


if __name__ == "__main__":
    main()
