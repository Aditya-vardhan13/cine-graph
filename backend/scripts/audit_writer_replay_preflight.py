"""Read-only preflight for retaining new identity captures as source snapshots."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import DataSource, SourceObject, SourceSnapshot
from app.services.snapshot_integrity import verify_snapshot_file
from scripts.audit_writer_identity_recovery import audit_recovery


def preflight(db, audit_path: Path, recovery_dir: Path, recovery_audit_path: Path) -> dict:
    reviewed_bytes = recovery_audit_path.read_bytes()
    recorded = json.loads(reviewed_bytes)
    recomputed = audit_recovery(audit_path, recovery_dir)
    if recorded != recomputed or not recomputed["complete"]:
        raise ValueError("Recovery audit must be complete and match the current captured bytes exactly.")
    checkpoint = json.loads((recovery_dir / "checkpoint.json").read_bytes())
    captures = checkpoint["captures"]
    passing = [entry for entry in recomputed["entries"] if entry["mechanical_checks_passed"]]
    ids = [UUID(captures[entry["qid"]]["previous_snapshot_id"]) for entry in passing]
    rows = db.execute(select(SourceSnapshot, SourceObject, DataSource)
        .join(SourceObject, SourceObject.id == SourceSnapshot.source_object_id)
        .join(DataSource, DataSource.id == SourceObject.source_id)
        .where(SourceSnapshot.id.in_(ids))).all()
    previous = {str(snapshot.id): (snapshot, obj, source) for snapshot, obj, source in rows}
    object_ids = {obj.id for _, obj, _ in rows}
    new_hashes = {entry["new_sha256"] for entry in passing}
    existing_rows = db.execute(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id.in_(object_ids), SourceSnapshot.content_hash.in_(new_hashes),
    )).scalars().all()
    existing = {(snap.source_object_id, snap.content_hash, str(snap.source_revision)): snap for snap in existing_rows}
    entries = []
    counts = Counter()
    for entry in recomputed["entries"]:
        qid = entry["qid"]
        capture = captures[qid]
        issues = list(entry["issues"])
        prior = previous.get(capture["previous_snapshot_id"])
        if entry["mechanical_checks_passed"]:
            if prior is None:
                issues.append("prior_snapshot_descriptor_missing")
            else:
                old, obj, source = prior
                if (source.name != "Wikidata" or obj.external_id != qid
                        or old.content_hash != capture["previous_sha256"]
                        or str(old.source_revision) != str(capture["previous_revision"])):
                    issues.append("prior_snapshot_descriptor_changed")
                new = existing.get((obj.id, capture["sha256"], str(capture["source_revision"])))
                if new is not None:
                    status = verify_snapshot_file(new.storage_uri, new.content_hash, new.byte_size)
                    issues.append("already_retained" if status == "verified" else "existing_new_snapshot_unavailable")
        state = "ready_for_source_retention" if not issues else "review_required"
        counts[state] += 1
        for issue in set(issues):
            counts[issue] += 1
        entries.append({"qid": qid, "film_title": entry["film_title"], "new_sha256": entry["new_sha256"],
                        "previous_snapshot_id": capture["previous_snapshot_id"],
                        "new_revision": capture["source_revision"], "status": state,
                        "issues": sorted(set(issues)), "identity_status": "review_required"})
    return {"schema": "cinegraph.writer-identity-replay-preflight/v1",
            "source_audit_sha256": recomputed["audit_sha256"],
            "recovery_audit_sha256": hashlib.sha256(reviewed_bytes).hexdigest(),
            "counts": dict(counts), "entries": entries,
            "note": "Read-only source-retention preflight; no identity or rights approvals."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("recovery_dir", type=Path)
    parser.add_argument("recovery_audit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing preflight report")
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        result = preflight(db, args.audit, args.recovery_dir, args.recovery_audit)
    data = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(data).hexdigest(), "counts": result["counts"]}))


if __name__ == "__main__":
    main()
