"""Prepare selected retained refreshes for guarded source-only replay; never approve them."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_article_html import PARSER_VERSION
from scripts.capture_writer_identity_recovery import local_output
from scripts.capture_writer_wikipedia_refresh import targets, verified_checkpoint


def manifest_for_capture(qid: str, capture: dict) -> dict:
    if (not re.fullmatch(r"Q[1-9][0-9]*", qid) or capture.get("status") != "review_candidate"
            or capture.get("metadata", {}).get("wikidata_id") != qid):
        raise ValueError("Capture is not an identity-matched review candidate")
    return {"schema": "cinegraph.wikipedia-review-capture/v1", "status": 200,
            "identity_status": "review_required", "rights_status": "review_required", "product_ingested": False,
            "sha256": capture["sha256"], "byte_size": capture["byte_size"],
            "storage_encoding": capture.get("storage_encoding", "identity"),
            "requested_url": capture["requested_url"], "canonical_url": capture["canonical_url"],
            "media_type": capture["media_type"], "retrieved_at": capture["retrieved_at"],
            "robots_sha256": capture["robots_sha256"], "metadata": capture["metadata"],
            "parser_version": PARSER_VERSION, "sections": capture["sections"],
            "prior_snapshot_id": capture["prior_snapshot_id"], "prior_sha256": capture["prior_sha256"],
            "prior_revision": capture["prior_revision"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("qids", nargs="+")
    args = parser.parse_args()
    audit_bytes = args.audit.read_bytes()
    rows = {row["wikidata_id"]: row for row in targets(json.loads(audit_bytes))}
    capture_dir = local_output(args.capture_dir)
    state = verified_checkpoint(capture_dir, hashlib.sha256(audit_bytes).hexdigest(), rows)
    if len(set(args.qids)) != len(args.qids):
        raise ValueError("Duplicate requested identities")
    prepared = []
    for qid in args.qids:
        capture = state["captures"].get(qid)
        if capture is None:
            raise ValueError(f"No retained capture for requested identity: {qid}")
        data = (json.dumps(manifest_for_capture(qid, capture), sort_keys=True, indent=2) + "\n").encode()
        path = capture_dir / "snapshots" / f"{qid}-{capture['sha256']}.review.json"
        prepared.append((qid, path, data))
    for qid, path, data in prepared:
        _write_immutable(path, data)
    print(json.dumps({"manifests": [{"manifest": str(path), "manifest_sha256": hashlib.sha256(data).hexdigest(),
                                     "qid": qid, "review_status": "review_required"}
                                    for qid, path, data in prepared]}))


if __name__ == "__main__":
    main()
