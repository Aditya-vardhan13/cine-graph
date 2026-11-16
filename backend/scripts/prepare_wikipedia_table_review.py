"""Prepare immutable, local table-review candidates from retained captures."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_article_tables import TABLE_PARSER_VERSION, extract_review_tables
from scripts.capture_writer_identity_recovery import local_output
from scripts.capture_writer_wikipedia_refresh import retained_payload
from scripts.prepare_writer_refresh_manifest import manifest_for_capture


def prepare(qid: str, capture: dict, payload: bytes, checkpoint_hash: str) -> dict:
    # This validates the capture's identity/review state, not reuse rights.
    manifest_for_capture(qid, capture)
    if hashlib.sha256(payload).hexdigest() != capture["sha256"] or len(payload) != capture["byte_size"]:
        raise ValueError("Retained source integrity mismatch")
    metadata, tables = extract_review_tables(payload, canonical_url=capture["canonical_url"], expected_qid=qid)
    expected = capture["metadata"]
    if (metadata.title != expected["title"] or metadata.page_id != expected["page_id"]
            or metadata.revision_id != expected["revision_id"]):
        raise ValueError("Capture metadata mismatch")
    return {"schema": "cinegraph.wikipedia-table-review/v1", "parser_version": TABLE_PARSER_VERSION,
            "checkpoint_sha256": checkpoint_hash, "source_sha256": capture["sha256"],
            "source_byte_size": len(payload), "source_url": capture["canonical_url"],
            "source_metadata": asdict(metadata), "identity_status": "review_required",
            "rights_status": "review_required", "product_ingested": False,
            "tables": [asdict(table) for table in tables]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("qids", nargs="+")
    parser.add_argument("--checkpoint-sha256", required=True)
    args = parser.parse_args()
    directory = local_output(args.capture_dir)
    checkpoint = (directory / "checkpoint.json").read_bytes()
    digest = hashlib.sha256(checkpoint).hexdigest()
    if digest != args.checkpoint_sha256:
        raise ValueError("Refresh checkpoint hash mismatch")
    if len(set(args.qids)) != len(args.qids):
        raise ValueError("Duplicate film identities")
    captures = json.loads(checkpoint)["captures"]
    results = []
    for qid in args.qids:
        capture = captures[qid]
        result = prepare(qid, capture, retained_payload(directory, capture), digest)
        data = (json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        path = directory / "snapshots" / f"{qid}-{capture['sha256']}-{TABLE_PARSER_VERSION}.table-review.json"
        results.append((qid, path, data, len(result["tables"])))
    for _, path, data, _ in results:
        _write_immutable(path, data)
    print(json.dumps({"candidates": [{"qid": qid, "path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                                      "tables": count} for qid, path, data, count in results]}))


if __name__ == "__main__":
    main()
