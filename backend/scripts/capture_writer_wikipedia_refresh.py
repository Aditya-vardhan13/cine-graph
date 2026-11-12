"""Capture current articles for a pinned writer identity audit, without ingestion."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

from app.core.config import get_settings
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_article_capture import WikipediaArticleFetcher
from app.services.wikipedia_article_html import ArticlePageParseError, parse_article_html
from scripts.capture_credit_targets import save_checkpoint
from scripts.capture_writer_identity_recovery import local_output


SCHEMA = "cinegraph.writer-wikipedia-refresh/v1"


def targets(audit: dict) -> list[dict]:
    if audit.get("schema") != "cinegraph.writer-source-identity-audit/v1" or audit.get("review_status") != "review_required":
        raise ValueError("Expected a review-only writer identity audit")
    selected = [row for row in audit.get("entries", []) if row.get("mechanical_checks_passed") is True]
    if len({row.get("wikidata_id") for row in selected}) != len(selected):
        raise ValueError("Writer identity audit contains duplicate or missing film QIDs")
    if any(not row.get("wikidata_id") or not str(row.get("wikipedia_page_id", "")).startswith("enwiki:") for row in selected):
        raise ValueError("Writer identity targets require a QID and Wikipedia page ID")
    return selected


def verified_checkpoint(output: Path, audit_hash: str, target_qids: set[str]) -> dict:
    checkpoint = output / "checkpoint.json"
    if not checkpoint.exists():
        return {"schema": SCHEMA, "audit_sha256": audit_hash, "captures": {}}
    state = json.loads(checkpoint.read_bytes())
    if state.get("schema") != SCHEMA or state.get("audit_sha256") != audit_hash:
        raise ValueError("Refresh checkpoint does not match the pinned audit")
    captures = state.get("captures")
    if not isinstance(captures, dict) or set(captures) - target_qids:
        raise ValueError("Refresh checkpoint contains unexpected identities")
    for qid, row in captures.items():
        if row.get("status") == "not_found":
            continue
        digest = row.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"Invalid retained content hash for {qid}")
        path = output / "snapshots" / f"{digest}.html"
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Retained capture missing or altered for {qid}")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000 or not 1.0 <= args.interval_seconds <= 10.0:
        parser.error("Use a limit of 1–1000 and a request interval of 1–10 seconds")
    audit_bytes = args.audit.read_bytes()
    audit_hash = hashlib.sha256(audit_bytes).hexdigest()
    rows = targets(json.loads(audit_bytes))
    output = local_output(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = verified_checkpoint(output, audit_hash, {row["wikidata_id"] for row in rows})
        pending = [row for row in rows if row["wikidata_id"] not in state["captures"]][:args.limit]
        if pending:
            if shutil.disk_usage(output).free < 6 * 1024**3:
                raise RuntimeError("Stopped before robots request: keep at least 6 GiB free")
            with WikipediaArticleFetcher(user_agent=get_settings().wikidata_user_agent,
                                         interval_seconds=args.interval_seconds) as fetcher:
                for row in pending:
                    if shutil.disk_usage(output).free < 6 * 1024**3:
                        raise RuntimeError("Stopped before request: keep at least 6 GiB free")
                    qid = row["wikidata_id"]
                    common = {"prior_snapshot_id": row["wikipedia_snapshot_id"],
                              "prior_sha256": row["wikipedia_sha256"],
                              "prior_revision": row["wikipedia_revision"], "requested_url": row["wikipedia_url"],
                              "retrieved_at": datetime.now(timezone.utc).isoformat(),
                              "robots_sha256": fetcher.robots_sha256, "identity_status": "review_required",
                              "rights_status": "review_required", "product_ingested": False}
                    try:
                        payload, canonical_url, _, media_type = fetcher.fetch(row["wikipedia_url"])
                    except FileNotFoundError:
                        state["captures"][qid] = {**common, "status": "not_found"}
                        save_checkpoint(output / "checkpoint.json", state)
                        print(f"not found {qid}: {len(state['captures'])}/{len(rows)}", flush=True)
                        continue
                    digest = hashlib.sha256(payload).hexdigest()
                    _write_immutable(output / "snapshots" / f"{digest}.html", payload)
                    issues = []
                    metadata = None
                    sections = []
                    try:
                        doc = parse_article_html(payload, canonical_url=canonical_url)
                        metadata = {"title": doc.metadata.title, "page_id": doc.metadata.page_id,
                                    "wikidata_id": doc.metadata.wikidata_id, "revision_id": doc.metadata.revision_id}
                        if doc.metadata.wikidata_id != qid:
                            issues.append("wikidata_id_mismatch")
                        if f"enwiki:{doc.metadata.page_id}" != row["wikipedia_page_id"]:
                            issues.append("page_id_mismatch")
                        if not doc.passages:
                            issues.append("no_extracted_passages")
                        sections = sorted({passage.section_locator for passage in doc.passages})
                    except ArticlePageParseError:
                        issues.append("article_parse_failed")
                    state["captures"][qid] = {**common, "status": "review_candidate" if not issues else "quarantined",
                                               "issues": issues, "sha256": digest, "byte_size": len(payload),
                                               "canonical_url": canonical_url, "media_type": media_type,
                                               "metadata": metadata, "sections": sections}
                    save_checkpoint(output / "checkpoint.json", state)
                    print(f"captured {qid}: {len(state['captures'])}/{len(rows)} ({state['captures'][qid]['status']})", flush=True)
        print(json.dumps({"captured": len(state["captures"]), "targets": len(rows),
                          "remaining": len(rows) - len(state["captures"]), "checkpoint": str(output / "checkpoint.json")}))


if __name__ == "__main__":
    main()
