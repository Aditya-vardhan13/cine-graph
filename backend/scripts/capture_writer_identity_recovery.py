"""Capture new Wikidata identity observations for unavailable retained snapshots.

The old snapshot descriptors are never rewritten. New response bytes and a
checkpoint remain local, and every item stays review-required.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil

from app.core.config import get_settings
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikidata_raw import WikidataEntityDataFetcher
from scripts.capture_credit_targets import save_checkpoint


SCHEMA = "cinegraph.writer-source-identity-audit/v1"
CHECKPOINT_SCHEMA = "cinegraph.writer-identity-recovery/v1"
QID = re.compile(r"Q[1-9][0-9]*\Z")


def recovery_targets(report: dict) -> list[dict]:
    if report.get("schema") != SCHEMA or report.get("review_status") != "review_required":
        raise ValueError("Expected a review-only writer source identity audit.")
    result = []
    seen = set()
    for row in report.get("entries", []):
        if "wikidata_snapshot_unavailable" not in row.get("issues", []):
            continue
        qid = row.get("wikidata_id")
        if not isinstance(qid, str) or not QID.fullmatch(qid) or qid in seen:
            raise ValueError("Recovery targets require unique valid Wikidata QIDs.")
        seen.add(qid)
        result.append(row)
    return result


def local_output(path: Path) -> Path:
    root = (Path(__file__).resolve().parents[2] / "data" / "evaluation").resolve()
    output = path.resolve()
    if not output.is_relative_to(root) or output == root:
        raise ValueError("Recovery output must be a child of the ignored data/evaluation directory.")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=10, help="Maximum new captures this invocation")
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000 or not 1.0 <= args.interval_seconds <= 10.0:
        parser.error("Use a limit of 1–1000 and a request interval of 1–10 seconds.")
    data = args.audit.read_bytes()
    targets = recovery_targets(json.loads(data))
    audit_hash = hashlib.sha256(data).hexdigest()
    output = local_output(args.output)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / "checkpoint.json"
    with (output / "capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if checkpoint.exists():
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
            if state.get("schema") != CHECKPOINT_SCHEMA or state.get("audit_sha256") != audit_hash:
                raise ValueError("Checkpoint does not match the exact audit report.")
        else:
            state = {"schema": CHECKPOINT_SCHEMA, "audit_sha256": audit_hash, "captures": {}}
        captured = state["captures"]
        for qid, item in captured.items():
            path = (output / item["snapshot_path"]).resolve()
            if not path.is_relative_to(output) or not path.is_file():
                raise ValueError(f"Retained recovery snapshot missing for {qid}.")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError(f"Retained recovery snapshot hash mismatch for {qid}.")
        pending = [row for row in targets if row["wikidata_id"] not in captured][:args.limit]
        if pending:
            with WikidataEntityDataFetcher(user_agent=get_settings().wikidata_user_agent,
                                           interval_seconds=args.interval_seconds) as fetcher:
                for row in pending:
                    if shutil.disk_usage(output).free < 6 * 1024**3:
                        raise RuntimeError("Stopped before request: keep at least 6 GiB free.")
                    qid = row["wikidata_id"]
                    capture = fetcher.fetch(qid)
                    digest = hashlib.sha256(capture.payload).hexdigest()
                    relative = Path("snapshots") / qid / f"{digest}.json"
                    _write_immutable(output / relative, capture.payload)
                    wiki_title = (capture.entity.get("sitelinks", {}).get("enwiki", {}) or {}).get("title")
                    expected_title = row["wikipedia_url"].split("/wiki/", 1)[-1]
                    from urllib.parse import unquote
                    expected_title = unquote(expected_title).replace("_", " ")
                    captured[qid] = {
                        "source_url": capture.canonical_url, "source_revision": capture.entity.get("lastrevid"),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(), "robots_sha256": fetcher.robots_sha256,
                        "sha256": digest, "snapshot_path": relative.as_posix(),
                        "previous_snapshot_id": row.get("wikidata_snapshot_id"),
                        "previous_revision": row.get("wikidata_revision"),
                        "previous_sha256": row.get("wikidata_sha256"),
                        "wikipedia_title": expected_title, "new_sitelink_title": wiki_title,
                        "sitelink_status": "matches" if wiki_title == expected_title else "review_required",
                        "identity_status": "review_required", "product_ingested": False,
                        "note": "New capture; not a replacement for the missing historical bytes.",
                    }
                    save_checkpoint(checkpoint, state)
                    print(f"captured {qid}: {len(captured)}/{len(targets)}", flush=True)
        print(json.dumps({"captured": len(captured), "targets": len(targets),
                          "remaining": len(targets) - len(captured), "checkpoint": str(checkpoint)}))


if __name__ == "__main__":
    main()
