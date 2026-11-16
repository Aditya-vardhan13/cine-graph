"""Compare two article parsers on retained refresh captures; no corpus writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_article_html import (COMBINED_REFERENCE_HEADINGS, COMBINED_REFERENCES_PARSER_VERSION,
                                                  _slug, parse_article_html)
from scripts.capture_writer_identity_recovery import local_output
from scripts.capture_writer_wikipedia_refresh import retained_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("refresh_dir", type=Path)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory, output = local_output(args.refresh_dir), local_output(args.output)
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing audit")
    raw = (directory / "checkpoint.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.checkpoint_sha256:
        raise ValueError("Refresh checkpoint hash mismatch")
    captures = json.loads(raw)["captures"]
    excluded_roots = {_slug(title) for title in COMBINED_REFERENCE_HEADINGS}
    counts = Counter()
    affected, errors = [], []
    for number, (qid, row) in enumerate(sorted(captures.items()), 1):
        if row.get("status") != "review_candidate":
            counts["excluded_capture_status"] += 1
            continue
        try:
            payload = retained_payload(directory, row)
            if hashlib.sha256(payload).hexdigest() != row["sha256"] or len(payload) != row["byte_size"]:
                raise ValueError("Retained source integrity mismatch")
            old = parse_article_html(payload, canonical_url=row["canonical_url"], expected_qid=qid)
            new = parse_article_html(payload, canonical_url=row["canonical_url"], expected_qid=qid,
                                     parser_version=COMBINED_REFERENCES_PARSER_VERSION)
            if old.metadata != new.metadata or str(old.metadata.revision_id) != str(row["metadata"]["revision_id"]):
                raise ValueError("Capture metadata differs")
            removed = [p for p in old.passages if p.section_locator.split("/", 1)[0].split("#", 1)[0] in excluded_roots]
            retained = [p for p in old.passages if p not in removed]
            if retained != list(new.passages):
                raise ValueError("Candidate changed content outside the intended reference headings")
            counts["checked"] += 1
            if removed:
                counts["articles_with_reference_passages"] += 1
                counts["reference_passages_removed"] += len(removed)
                affected.append({"qid": qid, "source_sha256": row["sha256"],
                                 "revision": row["metadata"]["revision_id"],
                                 "removed_sections": sorted({p.section_locator for p in removed}),
                                 "removed_passages": len(removed)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"qid": qid, "error": str(exc)})
        if number % 100 == 0:
            print(f"checked {number}/{len(captures)}", flush=True)
    report = {"schema": "cinegraph.combined-reference-parser-audit/v1", "checkpoint_sha256": args.checkpoint_sha256,
              "parser_version": COMBINED_REFERENCES_PARSER_VERSION, "counts": dict(counts), "errors": errors,
              "affected": affected, "product_ingested": False,
              "caution": "Detects configured heading differences only; not a completeness or semantic-quality proof."}
    _write_immutable(output, (json.dumps(report, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"counts": report["counts"], "errors": len(errors), "output": str(output)}))


if __name__ == "__main__":
    main()
