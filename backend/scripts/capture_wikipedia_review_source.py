"""Capture one current Wikipedia article for local, review-only comparison."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from app.core.config import get_settings
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_article_capture import WikipediaArticleFetcher
from app.services.wikipedia_article_html import parse_article_html
from scripts.capture_writer_identity_recovery import local_output


def validate_capture(payload: bytes, *, canonical_url: str, expected_qid: str, expected_page_id: int):
    document = parse_article_html(payload, canonical_url=canonical_url, expected_qid=expected_qid)
    if document.metadata.page_id != expected_page_id:
        raise ValueError("Captured article page ID differs from the expected retained identity")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("expected_qid")
    parser.add_argument("expected_page_id", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = local_output(args.output)
    if output.exists():
        raise FileExistsError("Refusing to overwrite a review capture")
    output.mkdir(parents=True)
    if shutil.disk_usage(output).free < 6 * 1024**3:
        raise RuntimeError("At least 6 GiB free space is required before capture")
    with WikipediaArticleFetcher(user_agent=get_settings().wikidata_user_agent) as fetcher:
        payload, canonical_url, status, media_type = fetcher.fetch(args.url)
        robots_sha256 = fetcher.robots_sha256
    digest = hashlib.sha256(payload).hexdigest()
    # Retain exact response bytes even if parsing or identity verification fails.
    _write_immutable(output / f"{digest}.html", payload)
    document = validate_capture(payload, canonical_url=canonical_url, expected_qid=args.expected_qid,
                                expected_page_id=args.expected_page_id)
    report = {"schema": "cinegraph.wikipedia-review-capture/v1", "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "requested_url": args.url, "canonical_url": canonical_url, "status": status, "media_type": media_type,
              "robots_sha256": robots_sha256, "sha256": digest, "byte_size": len(payload),
              "metadata": asdict(document.metadata), "parser_version": document.parser_version,
              "sections": sorted({passage.section_locator for passage in document.passages}),
              "identity_status": "review_required", "rights_status": "review_required", "product_ingested": False}
    encoded = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    _write_immutable(output / "manifest.json", encoded)
    print(json.dumps({"output": str(output), "sha256": digest, "metadata": report["metadata"],
                      "sections": report["sections"]}))


if __name__ == "__main__":
    main()
