"""Recheck held candidates against current sources before source-only replay."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import NarrativePassage
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikipedia_article_html import parse_article_html
from app.services.wikipedia_research import _snapshot_for_qid
from scripts.audit_writer_refresh_delta import classify, measurements
from scripts.capture_credit_targets import save_checkpoint
from scripts.capture_writer_identity_recovery import local_output
from scripts.capture_writer_wikipedia_refresh import retained_payload, targets, verified_checkpoint
from scripts.prepare_writer_refresh_manifest import manifest_for_capture
from scripts.replay_wikipedia_review_source import replay


def revision_action(current: str, capture: str) -> str:
    if not current.isdigit() or not capture.isdigit():
        raise ValueError("Source revisions must be numeric")
    return "newer" if int(capture) > int(current) else "same" if int(capture) == int(current) else "older"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("batch_checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required for source-only replay")
    audit, directory, batch_path, output = map(local_output, (args.audit, args.capture_dir, args.batch_checkpoint, args.output))
    audit_bytes, batch_bytes = audit.read_bytes(), batch_path.read_bytes()
    audit_hash, batch_hash = hashlib.sha256(audit_bytes).hexdigest(), hashlib.sha256(batch_bytes).hexdigest()
    batch = json.loads(batch_bytes)
    if batch.get("schema") != "cinegraph.writer-refresh-source-replay/v1" or batch.get("audit_sha256") != audit_hash:
        raise ValueError("Batch checkpoint does not match identity audit")
    rows = {row["wikidata_id"]: row for row in targets(json.loads(audit_bytes))}
    captures = verified_checkpoint(directory, audit_hash, rows)["captures"]
    held = [qid for qid, item in batch["items"].items() if item.get("status") == "review_required"]
    if any(qid not in captures or captures[qid]["status"] != "review_candidate" for qid in held):
        raise ValueError("Held selection contains a missing or quarantined capture")
    output.parent.mkdir(parents=True, exist_ok=True)
    with (output.parent / "held-source-replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(output.read_bytes()) if output.exists() else {
            "schema": "cinegraph.held-source-replay/v1", "batch_sha256": batch_hash, "items": {}}
        if (state.get("schema") != "cinegraph.held-source-replay/v1" or state.get("batch_sha256") != batch_hash
                or set(state.get("items", {})) - set(held)):
            raise ValueError("Held replay checkpoint does not match batch")
        storage = Path(get_settings().raw_snapshot_root)
        for qid in held:
            if qid in state["items"]:
                continue
            if shutil.disk_usage(directory).free < 6 * 1024**3 or shutil.disk_usage(storage).free < 6 * 1024**3:
                raise RuntimeError("Stopped before replay: keep at least 6 GiB free")
            capture = captures[qid]
            with SessionLocal() as db:
                current = _snapshot_for_qid(db, qid)
                if verify_snapshot_file(current.storage_uri, current.content_hash, current.byte_size) != "verified":
                    raise ValueError(f"Current snapshot bytes failed integrity: {qid}")
                action = revision_action(str(current.source_revision), str(capture["metadata"]["revision_id"]))
                if action == "same" and current.content_hash == capture["sha256"]:
                    result = {"qid": qid, "snapshot_id": str(current.id), "created": False,
                              "status": "previously_replayed", "source_revision": current.source_revision}
                elif action != "newer":
                    result = {"qid": qid, "status": "review_required", "reason": f"capture_revision_{action}"}
                else:
                    passages = db.scalars(select(NarrativePassage).where(NarrativePassage.source_snapshot_id == current.id)).all()
                    if (not passages or len({p.extraction_version for p in passages}) != 1
                            or any(hashlib.sha256(p.content.encode()).hexdigest() != p.content_hash for p in passages)):
                        raise ValueError(f"Current passage extraction failed integrity: {qid}")
                    old = measurements((p.section_locator, p.content) for p in passages)
                    document = parse_article_html(retained_payload(directory, capture), canonical_url=capture["canonical_url"], expected_qid=qid)
                    new = measurements((p.section_locator, p.content) for p in document.passages)
                    if classify(old, new) != "story_present_both":
                        result = {"qid": qid, "status": "review_required", "reason": "current_story_difference"}
                    else:
                        rebound = {**capture, "prior_snapshot_id": str(current.id), "prior_sha256": current.content_hash,
                                   "prior_revision": current.source_revision}
                        data = (json.dumps(manifest_for_capture(qid, rebound), sort_keys=True, indent=2) + "\n").encode()
                        path = directory / "snapshots" / f"{qid}-{capture['sha256']}-{current.content_hash}.review.json"
                        _write_immutable(path, data)
                        try:
                            result = replay(db, manifest_path=path, expected_manifest_sha256=hashlib.sha256(data).hexdigest(), storage_root=storage)
                        except ValueError as exc:
                            db.rollback()
                            allowed = ("does not match the pinned prior snapshot", "Previously approved source",
                                       "Published writer film", "Existing film identity must match", "existing QID is not bound")
                            if not any(part in str(exc) for part in allowed):
                                raise
                            result = {"qid": qid, "status": "review_required", "reason": str(exc)}
            state["items"][qid] = result
            save_checkpoint(output, state)
            print(json.dumps({"processed": len(state["items"]), "selected": len(held), "result": result}), flush=True)
    print(json.dumps({"processed": len(state["items"]), "selected": len(held)}))


if __name__ == "__main__":
    main()
