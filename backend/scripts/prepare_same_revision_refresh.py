"""Bind a retained HTML capture to the exact current same-revision source.

This prepares a review-only manifest; it never writes to the corpus database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CanonicalEntity, SourceObject
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.current_narrative_passages import current_passage_rows
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikipedia_article_html import parse_article_html
from app.services.wikipedia_research import _snapshot_for_qid
from scripts.capture_writer_identity_recovery import local_output
from scripts.capture_writer_wikipedia_refresh import retained_payload
from scripts.prepare_writer_refresh_manifest import manifest_for_capture


def normalized_story(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", " ".join(parts))).strip()


def prepare(db: Session, *, qid: str, capture: dict, payload: bytes,
            expected_snapshot_id: UUID, expected_snapshot_hash: str) -> dict:
    if hashlib.sha256(payload).hexdigest() != capture.get("sha256") or len(payload) != capture.get("byte_size"):
        raise ValueError("Captured article integrity mismatch")
    document = parse_article_html(payload, canonical_url=capture["canonical_url"], expected_qid=qid)
    metadata = capture.get("metadata") or {}
    if (metadata.get("page_id") != document.metadata.page_id
            or metadata.get("revision_id") != document.metadata.revision_id
            or metadata.get("title") != document.metadata.title):
        raise ValueError("Capture metadata differs from retained article")
    snapshot = _snapshot_for_qid(db, qid)
    obj = db.get(SourceObject, snapshot.source_object_id)
    entity = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == qid))
    if (snapshot.id != expected_snapshot_id or snapshot.content_hash != expected_snapshot_hash
            or verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified"
            or not obj or obj.external_id != f"enwiki:{document.metadata.page_id}"
            or str(snapshot.source_revision) != str(document.metadata.revision_id)
            or not entity or entity.entity_kind != "film" or entity.lifecycle_status != "active"):
        raise ValueError("Current source identity, revision or integrity mismatch")
    current = [p for p, s in current_passage_rows(db, {entity.id}) if s.id == snapshot.id]
    old = sorted((p for p in current if p.section_locator == "plot"), key=lambda p: p.ordinal)
    new = sorted((p for p in document.passages if p.section_locator == "plot"), key=lambda p: p.ordinal)
    if not old or not new or any(hashlib.sha256(p.content.encode()).hexdigest() != p.content_hash for p in old):
        raise ValueError("Current story passages are missing or fail integrity")
    if normalized_story([p.content for p in old]) != normalized_story([p.content for p in new]):
        raise ValueError("Story text differs; explicit content review is required")
    # Plot equality alone does not protect awards, distribution, or other
    # non-story material. This conservative screen is not a claim of semantic
    # equivalence; it prevents obviously lossy replacements from being prepared.
    old_lengths: dict[str, int] = defaultdict(int)
    new_lengths: dict[str, int] = defaultdict(int)
    for passage in current:
        old_lengths[passage.section_locator] += len(passage.content)
    for passage in document.passages:
        new_lengths[passage.section_locator] += len(passage.content)
    reduced = sorted(locator for locator, length in old_lengths.items()
                     if new_lengths[locator] * 4 < length * 3)
    if reduced:
        raise ValueError(f"Section coverage reduced; explicit content review is required: {', '.join(reduced)}")
    rebound = {**capture, "prior_snapshot_id": str(snapshot.id), "prior_sha256": snapshot.content_hash,
               "prior_revision": snapshot.source_revision}
    return {**manifest_for_capture(qid, rebound), "story_comparison": "nfc-whitespace-exact-v1",
            "section_coverage_check": "minimum-75-percent-characters-v1"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("qid")
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--expected-snapshot-id", required=True, type=UUID)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    args = parser.parse_args()
    directory = local_output(args.capture_dir)
    checkpoint = (directory / "checkpoint.json").read_bytes()
    if hashlib.sha256(checkpoint).hexdigest() != args.checkpoint_sha256:
        raise ValueError("Refresh checkpoint hash mismatch")
    capture = json.loads(checkpoint)["captures"][args.qid]
    payload = retained_payload(directory, capture)
    with SessionLocal() as db:
        result = prepare(db, qid=args.qid, capture=capture, payload=payload,
                         expected_snapshot_id=args.expected_snapshot_id, expected_snapshot_hash=args.expected_snapshot_sha256)
    data = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    path = directory / "snapshots" / f"{args.qid}-{capture['sha256']}-{args.expected_snapshot_id}.review.json"
    _write_immutable(path, data)
    print(json.dumps({"qid": args.qid, "manifest": str(path), "manifest_sha256": hashlib.sha256(data).hexdigest(),
                      "identity_status": "review_required"}))


if __name__ == "__main__":
    main()
