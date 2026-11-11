"""Retain preflighted new Wikidata captures as source evidence, not film facts."""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.wikidata_raw import entity_from_entitydata, ingest_entities
from scripts.audit_writer_replay_preflight import preflight


def replay(db: Session, *, plan: dict, plan_hash: str, audit_path: Path,
           recovery_dir: Path, recovery_audit_path: Path, snapshot_root: Path,
           disk_check_path: Path, limit: int, batch_size: int = 10) -> dict:
    if plan.get("schema") != "cinegraph.writer-identity-replay-preflight/v1":
        raise ValueError("Expected a writer source replay preflight.")
    if not 1 <= limit <= 1000 or not 1 <= batch_size <= 20:
        raise ValueError("Use a limit of 1–1000 and batch size of 1–20.")
    current = preflight(db, audit_path, recovery_dir, recovery_audit_path)
    if (current["source_audit_sha256"], current["recovery_audit_sha256"]) != (
        plan.get("source_audit_sha256"), plan.get("recovery_audit_sha256")
    ):
        raise ValueError("Source or recovery audit fingerprint changed since preflight.")
    original = {row["qid"]: row for row in plan["entries"]}
    now = {row["qid"]: row for row in current["entries"]}
    if len(original) != len(plan["entries"]) or set(original) != set(now):
        raise ValueError("Preflight QID set changed or contains duplicates.")
    for qid, row in original.items():
        latest = now[qid]
        if any(row.get(k) != latest.get(k) for k in ("new_sha256", "previous_snapshot_id", "new_revision")):
            raise ValueError(f"Preflight source identity changed for {qid}.")
        if row["status"] == "ready_for_source_retention":
            if latest["status"] != "ready_for_source_retention" and latest["issues"] != ["already_retained"]:
                raise ValueError(f"Previously eligible source {qid} no longer passes preflight: {latest['issues']}.")
        elif row["status"] != "review_required":
            raise ValueError("Unexpected preflight status.")
    checkpoint = json.loads((recovery_dir / "checkpoint.json").read_bytes())
    targets = [qid for qid, row in original.items()
               if row["status"] == "ready_for_source_retention" and now[qid]["status"] == "ready_for_source_retention"][:limit]
    counts = Counter()
    counts["eligible_in_plan"] = sum(row["status"] == "ready_for_source_retention" for row in original.values())
    counts["already_retained"] = sum(original[qid]["status"] == "ready_for_source_retention"
                                     and now[qid]["issues"] == ["already_retained"] for qid in original)
    counts["quarantined_in_plan"] = len(original) - counts["eligible_in_plan"]
    for offset in range(0, len(targets), batch_size):
        if shutil.disk_usage(disk_check_path).free < 6 * 1024**3:
            raise RuntimeError("Stopped before batch: keep at least 6 GiB free on the host-backed path.")
        qids = targets[offset:offset + batch_size]
        payloads, entities = {}, {}
        robots = set()
        for qid in qids:
            capture = checkpoint["captures"][qid]
            path = (recovery_dir / capture["snapshot_path"]).resolve()
            if not path.is_relative_to(recovery_dir.resolve()):
                raise ValueError("Capture path escaped the recovery directory.")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != original[qid]["new_sha256"]:
                raise ValueError(f"Capture hash changed for {qid}.")
            payloads[qid] = payload
            entities[qid] = entity_from_entitydata(json.loads(payload), qid)
            robots.add(capture["robots_sha256"])
        if len(robots) != 1:
            raise ValueError("A replay batch cannot combine different robots policy fingerprints.")
        result = ingest_entities(db, entities, raw_payloads=payloads, snapshot_root=snapshot_root,
                                 manifest_uri=f"writer-identity-replay:{plan_hash}",
                                 manifest_sha256=plan_hash, robots_sha256=next(iter(robots)))
        counts["processed"] += len(qids)
        counts["new_snapshots"] += result["snapshots"]
        counts["source_assertions"] += result["source_assertions"]
        print(f"source snapshots retained: {counts['processed']}/{len(targets)}", flush=True)
    counts["remaining"] = counts["eligible_in_plan"] - counts["already_retained"] - counts["processed"]
    return {"schema": "cinegraph.writer-identity-source-replay/v1", "preflight_sha256": plan_hash,
            "counts": dict(counts), "note": "New raw source snapshots and source assertions only; no operational facts or approvals."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("recovery_dir", type=Path)
    parser.add_argument("recovery_audit", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--disk-check-path", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required; run the read-only preflight first")
    plan_bytes = args.plan.read_bytes()
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    if plan_hash != args.expected_plan_sha256:
        raise ValueError("Preflight report hash does not match the explicit expected digest.")
    # The lock belongs to the ignored recovery directory, shared by all runs.
    with (args.recovery_dir / "replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with SessionLocal() as db:
            result = replay(db, plan=json.loads(plan_bytes), plan_hash=plan_hash, audit_path=args.audit,
                            recovery_dir=args.recovery_dir, recovery_audit_path=args.recovery_audit,
                            snapshot_root=args.snapshot_root, disk_check_path=args.disk_check_path,
                            limit=args.limit, batch_size=args.batch_size)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
