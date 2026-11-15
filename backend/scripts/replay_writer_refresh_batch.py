"""Replay selected story-present candidates locally, without rights or publication decisions."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.catalog_pilot_reextract import _write_immutable
from scripts.capture_credit_targets import save_checkpoint
from scripts.capture_writer_identity_recovery import local_output
from scripts.capture_writer_wikipedia_refresh import targets, verified_checkpoint
from scripts.prepare_writer_refresh_manifest import manifest_for_capture
from scripts.replay_wikipedia_review_source import replay


SCHEMA = "cinegraph.writer-refresh-source-replay/v1"


def select_qids(report: dict) -> list[str]:
    if (report.get("schema") != "cinegraph.writer-refresh-story-delta/v3"
            or report.get("review_status") != "review_required"):
        raise ValueError("Unexpected review-only source comparison report")
    qids = [item["qid"] for item in report["entries"] if item.get("classification") == "story_present_both"]
    if len(qids) != len(set(qids)):
        raise ValueError("Duplicate source candidates")
    return qids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply or not 1 <= args.limit <= 1000:
        parser.error("--apply and a limit between 1 and 1000 are required")
    audit_path, capture_dir, comparison_path, checkpoint = map(local_output, (args.audit, args.capture_dir, args.comparison, args.checkpoint))
    audit_bytes, comparison_bytes = audit_path.read_bytes(), comparison_path.read_bytes()
    audit_hash, comparison_hash = hashlib.sha256(audit_bytes).hexdigest(), hashlib.sha256(comparison_bytes).hexdigest()
    rows = {row["wikidata_id"]: row for row in targets(json.loads(audit_bytes))}
    comparison = json.loads(comparison_bytes)
    if comparison.get("audit_sha256") != audit_hash:
        raise ValueError("Comparison is bound to another identity audit")
    qids = select_qids(comparison)
    captures = verified_checkpoint(capture_dir, audit_hash, rows)["captures"]
    if any(qid not in captures or captures[qid]["status"] != "review_candidate" for qid in qids):
        raise ValueError("Comparison contains a missing or quarantined capture")
    compared = {row["qid"]: row for row in comparison["entries"]}
    for qid in qids:
        if (compared[qid].get("capture_sha256") != captures[qid]["sha256"]
                or compared[qid].get("prior_snapshot_id") != captures[qid]["prior_snapshot_id"]
                or compared[qid].get("prior_sha256") != captures[qid]["prior_sha256"]):
            raise ValueError(f"Comparison source fingerprint mismatch: {qid}")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with (checkpoint.parent / "source-replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(checkpoint.read_bytes()) if checkpoint.exists() else {
            "schema": SCHEMA, "audit_sha256": audit_hash, "comparison_sha256": comparison_hash, "items": {}}
        if (state.get("schema") != SCHEMA or state.get("audit_sha256") != audit_hash
                or state.get("comparison_sha256") != comparison_hash or set(state.get("items", {})) - set(qids)):
            raise ValueError("Replay checkpoint does not match the frozen selection")
        pending = [qid for qid in qids if qid not in state["items"]][:args.limit]
        storage = Path(get_settings().raw_snapshot_root)
        for qid in pending:
            if shutil.disk_usage(capture_dir).free < 6 * 1024**3 or shutil.disk_usage(storage).free < 6 * 1024**3:
                raise RuntimeError("Stopped before replay: keep at least 6 GiB free")
            capture = captures[qid]
            manifest = (json.dumps(manifest_for_capture(qid, capture), sort_keys=True, indent=2) + "\n").encode()
            manifest_path = capture_dir / "snapshots" / f"{qid}-{capture['sha256']}.review.json"
            _write_immutable(manifest_path, manifest)
            with SessionLocal() as db:
                try:
                    result = replay(db, manifest_path=manifest_path,
                                    expected_manifest_sha256=hashlib.sha256(manifest).hexdigest(), storage_root=storage)
                except ValueError as exc:
                    db.rollback()
                    reason = str(exc)
                    allowed = ("does not match the pinned prior snapshot", "Previously approved source",
                               "Published writer film", "Existing film identity must match", "existing QID is not bound")
                    if not any(part in reason for part in allowed):
                        raise
                    result = {"qid": qid, "status": "review_required", "reason": reason}
            state["items"][qid] = result
            save_checkpoint(checkpoint, state)
            print(json.dumps({"processed": len(state["items"]), "selected": len(qids), "result": result}), flush=True)
    print(json.dumps({"processed": len(state["items"]), "selected": len(qids), "remaining": len(qids) - len(state["items"])}))


if __name__ == "__main__":
    main()
