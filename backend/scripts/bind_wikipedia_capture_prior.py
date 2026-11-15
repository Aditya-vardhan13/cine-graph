"""Bind a retained single-article capture to its audited prior snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_article_html import parse_article_html
from scripts.capture_writer_identity_recovery import local_output


def bind(manifest: dict, row: dict, payload: bytes) -> dict:
    if (manifest.get("schema") != "cinegraph.wikipedia-review-capture/v1"
            or manifest.get("status") != 200 or manifest.get("identity_status") != "review_required"
            or manifest.get("rights_status") != "review_required" or manifest.get("product_ingested") is not False
            or hashlib.sha256(payload).hexdigest() != manifest.get("sha256")
            or len(payload) != manifest.get("byte_size")):
        raise ValueError("Capture is not intact, successful, and review-only")
    qid = row["wikidata_id"]
    doc = parse_article_html(payload, canonical_url=manifest["canonical_url"], expected_qid=qid)
    if (f"enwiki:{doc.metadata.page_id}" != row["wikipedia_page_id"]
            or doc.metadata.page_id != manifest["metadata"]["page_id"]
            or doc.metadata.revision_id != manifest["metadata"]["revision_id"]
            or doc.metadata.title != manifest["metadata"]["title"]):
        raise ValueError("Capture page identity or revision does not match audited source")
    return {**manifest, "prior_snapshot_id": row["wikipedia_snapshot_id"],
            "prior_sha256": row["wikipedia_sha256"], "prior_revision": row["wikipedia_revision"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("qid")
    args = parser.parse_args()
    audit_path, manifest_path = local_output(args.audit), local_output(args.manifest)
    audit = json.loads(audit_path.read_bytes())
    if audit.get("schema") != "cinegraph.writer-source-identity-audit/v1" or audit.get("review_status") != "review_required":
        raise ValueError("Expected a review-only source audit")
    rows = [row for row in audit["entries"] if row.get("wikidata_id") == args.qid]
    if len(rows) != 1:
        raise ValueError("Expected one audited identity")
    manifest = json.loads(manifest_path.read_bytes())
    digest = manifest.get("sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid source digest")
    payload = (manifest_path.parent / f"{digest}.html").read_bytes()
    bound = bind(manifest, rows[0], payload)
    data = (json.dumps(bound, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    prior_id = str(UUID(rows[0]["wikipedia_snapshot_id"]))
    output = manifest_path.parent / f"{digest}-{prior_id}.review.json"
    _write_immutable(output, data)
    print(json.dumps({"manifest": str(output), "manifest_sha256": hashlib.sha256(data).hexdigest(),
                      "qid": args.qid, "identity_status": "review_required"}))


if __name__ == "__main__":
    main()
