"""Replay a retained review capture and its passages as one database transaction.

Only films without approved narrative sources or writer memberships may use
this conservative path. It creates no model-use decisions or typed facts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.core.config import get_settings
from app.models import (CanonicalEntity, Film, NarrativeUseDecision, RawIngestionRun,
                        ReferenceCollectionMembership, SourceObject, SourceSnapshot)
from app.services.wikipedia_article_html import parse_article_html
from app.services.raw_snapshots import store_payload
from app.services.wikipedia_raw import (ADAPTER_VERSION, persist_article_snapshot,
                                         source_for_wikipedia, validate_article_capture_hashes,
                                         wikipedia_article_html_policy)
from app.services.wikipedia_research import _snapshot_for_qid, extract_passages
from scripts.capture_writer_identity_recovery import local_output


def replay(db: Session, *, manifest_path: Path, expected_manifest_sha256: str, storage_root: Path) -> dict:
    if not storage_root.is_dir() or shutil.disk_usage(storage_root).free < 6 * 1024**3:
        raise ValueError("Existing snapshot storage requires at least 6 GiB free")
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
        raise ValueError("Review capture manifest hash mismatch")
    manifest = json.loads(manifest_bytes)
    validate_article_capture_hashes(robots_sha256=manifest.get("robots_sha256"),
                                    manifest_sha256=expected_manifest_sha256)
    if (manifest.get("schema") != "cinegraph.wikipedia-review-capture/v1"
            or manifest.get("identity_status") != "review_required"
            or manifest.get("rights_status") != "review_required"
            or manifest.get("product_ingested") is not False
            or manifest.get("status") != 200 or manifest.get("media_type") not in {"text/html", "application/xhtml+xml"}):
        raise ValueError("Not a successful review-only capture")
    digest = manifest["sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid capture digest")
    payload = (manifest_path.parent / f"{digest}.html").read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest or len(payload) != manifest["byte_size"]:
        raise ValueError("Captured article bytes do not match the manifest")
    metadata = manifest["metadata"]
    document = parse_article_html(payload, canonical_url=manifest["canonical_url"], expected_qid=metadata["wikidata_id"])
    if (document.metadata.page_id != metadata["page_id"] or document.metadata.revision_id != metadata["revision_id"]
            or document.metadata.title != metadata["title"] or not document.passages):
        raise ValueError("Captured article metadata or passages disagree with the manifest")
    qid = metadata["wikidata_id"]
    entity = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == qid).with_for_update())
    film = db.scalar(select(Film).where(Film.entity_id == entity.id)) if entity else None
    if not entity or entity.entity_kind != "film" or entity.lifecycle_status != "active" or not film or film.wikidata_id != qid:
        raise ValueError("Existing film identity must match the capture")
    source = source_for_wikipedia(db)
    obj = db.scalar(select(SourceObject).where(SourceObject.source_id == source.id,
                    SourceObject.external_id == f"enwiki:{metadata['page_id']}"))
    if obj is None:
        raise ValueError("Expected existing Wikipedia source object was not found")
    old = _snapshot_for_qid(db, qid)
    if old.source_object_id != obj.id:
        raise ValueError("The existing QID is not bound to this Wikipedia page")
    if db.scalar(select(NarrativeUseDecision.id).join(SourceSnapshot).where(
            SourceSnapshot.source_object_id == obj.id, NarrativeUseDecision.decision == "approved").limit(1)):
        raise ValueError("Previously approved source requires explicit lifecycle review")
    if db.scalar(select(ReferenceCollectionMembership.id).where(
            ReferenceCollectionMembership.entity_id == entity.id,
            ReferenceCollectionMembership.collection_code == get_settings().writer_catalog_collection_code,
            ReferenceCollectionMembership.status == "included").limit(1)):
        raise ValueError("Published writer film requires explicit lifecycle review")
    policy = wikipedia_article_html_policy(db, source, robots_sha256=manifest["robots_sha256"])
    manifest_uri, retained_hash = store_payload(source.id, manifest_bytes, suffix=".review.json", root=storage_root)
    if (retained_hash != expected_manifest_sha256
            or hashlib.sha256(Path(unquote(urlsplit(manifest_uri).path)).read_bytes()).hexdigest() != retained_hash):
        raise ValueError("Retained manifest hash mismatch")
    run = RawIngestionRun(source_id=source.id, access_policy_id=policy.id,
                          adapter_name="wikipedia_review_capture_replay", adapter_version=ADAPTER_VERSION,
                          manifest_uri=manifest_uri, manifest_hash=expected_manifest_sha256,
                          status="running", records_requested=1, started_at=datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    stored, created, assertions = persist_article_snapshot(db, source=source, run=run, payload=payload,
                                                          document=document, media_type=manifest["media_type"],
                                                          storage_root=storage_root)
    db.flush()
    if _snapshot_for_qid(db, qid).id != stored.id:
        raise ValueError("Replayed snapshot is not the latest resolved QID source")
    run.records_snapshotted = int(created)
    run.status = "complete"
    run.completed_at = datetime.now(timezone.utc)
    # extract_passages commits after all passage rows are inserted; a failure
    # before that point leaves both source metadata and passages uncommitted.
    result = extract_passages(db, qid)
    return {"qid": qid, "snapshot_id": str(stored.id), "created": created,
            "source_assertions_created": assertions, "passages_created": result["passages_created"],
            "source_revision": result["source_revision"], "rights_status": "review_required"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required to write source snapshots and passages")
    with SessionLocal() as db:
        try:
            result = replay(db, manifest_path=local_output(args.manifest),
                            expected_manifest_sha256=args.manifest_sha256,
                            storage_root=Path(get_settings().raw_snapshot_root))
        except Exception:
            db.rollback()
            raise
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
