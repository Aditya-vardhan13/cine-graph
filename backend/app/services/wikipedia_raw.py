"""Robots-compliant English Wikipedia article snapshots and legacy API guards."""
from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DataSource, RawIngestionRun, SourceAccessPolicy, SourceSnapshot
from app.services.wikipedia_article_capture import WikipediaArticleFetcher
from app.services.wikipedia_article_html import ArticleDocument, article_url, parse_article_html
from app.services.raw_snapshots import source_assertion, source_object, snapshot

SOURCE_URL = "https://en.wikipedia.org/"
SOURCE_NAME = "English Wikipedia"
ADAPTER_VERSION = "enwiki-article-html-capture-v1"


def request_interval_seconds() -> float:
    return get_settings().source_request_interval_seconds


class RawWikipediaError(RuntimeError):
    pass


def validate_article_capture_hashes(
    *, robots_sha256: str, manifest_sha256: str | None,
) -> None:
    """Validate source-policy and replay-manifest fingerprints before writes."""
    for label, value in (("robots.txt", robots_sha256), ("manifest", manifest_sha256)):
        if (label == "robots.txt" and value is None) or (value is not None and (
            not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        )):
            raise RawWikipediaError(f"{label} SHA-256 must be 64 lowercase hexadecimal characters.")


def page_lookup_record(title: str, page: Any) -> dict[str, Any] | None:
    """Convert one resolved wikipedia-api page into a stable local record."""
    if not page.exists():
        return None
    return {
        "requested_title": title,
        "resolved_title": page.title,
        "pageid": page.pageid,
        "fullurl": page.fullurl,
        "section_titles": [section.title for section in page.sections],
    }


def source_for_wikipedia(db: Session) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if source:
        source.notes = (
            "English article pages are captured only through robots-permitted /wiki/ paths. "
            "Generic Action API routes are disabled. Article content is attributed CC BY-SA 4.0."
        )
        return source
    source = DataSource(
        name=SOURCE_NAME,
        url=SOURCE_URL,
        source_type="revisioned_narrative_context",
        license="CC BY-SA 4.0",
        rights_status="attributed_reuse",
        notes=(
            "English article pages are captured only through robots-permitted /wiki/ paths. "
            "Generic Action API routes are disabled. Article content is attributed CC BY-SA 4.0."
        ),
    )
    db.add(source)
    db.flush()
    return source


def wikipedia_api_policy(db: Session, source: DataSource) -> SourceAccessPolicy:
    policy = db.scalar(select(SourceAccessPolicy).where(
        SourceAccessPolicy.source_id == source.id,
        SourceAccessPolicy.access_mode == "api",
    ))
    if policy:
        policy.max_requests_per_minute = get_settings().source_requests_per_minute
        policy.robots_url = "https://en.wikipedia.org/robots.txt"
        policy.robots_decision = "disallow_generic_api"
        policy.allowed_paths = []
        if policy.decision == "allowed":
            policy.decision = "review_required"
        policy.decision_notes = (
            "Current robots.txt disallows /w/ except action=mobileview; a live check found "
            "mobileview is no longer a recognized action. Generic Action API fetching is disabled "
            "until an allowed article-page capture adapter is reviewed and tested."
        )
        return policy
    policy = SourceAccessPolicy(
        source_id=source.id,
        access_mode="api",
        policy_url="https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy",
        robots_url="https://en.wikipedia.org/robots.txt",
        robots_decision="disallow_generic_api",
        allowed_paths=[],
        required_user_agent=True,
        max_requests_per_minute=get_settings().source_requests_per_minute,
        max_concurrency=1,
        decision="review_required",
        decision_notes=(
            "Current robots.txt disallows /w/ except action=mobileview; a live check found "
            "mobileview is no longer a recognized action. Generic Action API fetching is disabled "
            "until an allowed article-page capture adapter is reviewed and tested."
        ),
    )
    db.add(policy)
    db.flush()
    return policy


def wikipedia_article_html_policy(db: Session, source: DataSource, *, robots_sha256: str) -> SourceAccessPolicy:
    """Record the explicitly checked robots permission for ordinary article paths."""
    policy = db.scalar(select(SourceAccessPolicy).where(
        SourceAccessPolicy.source_id == source.id,
        SourceAccessPolicy.access_mode == "html",
    ))
    if policy and policy.decision == "denied":
        raise RawWikipediaError("The registered Wikipedia HTML policy is denied; refusing to fetch.")
    if policy is None:
        policy = SourceAccessPolicy(
            source_id=source.id,
            access_mode="html",
            policy_url="https://en.wikipedia.org/robots.txt",
            robots_url="https://en.wikipedia.org/robots.txt",
            robots_decision="allow_article_path",
            allowed_paths=["https://en.wikipedia.org/wiki/*"],
            required_user_agent=True,
            max_requests_per_minute=min(60, get_settings().source_requests_per_minute),
            max_concurrency=1,
            decision="allowed",
            decision_notes="Ordinary /wiki/{article} paths were checked against live robots.txt; "
                           f"robots SHA-256 {robots_sha256}. Generic /w/api.php remains disabled.",
            policy_revision=f"robots-sha256:{robots_sha256}",
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
    else:
        policy.robots_url = "https://en.wikipedia.org/robots.txt"
        policy.robots_decision = "allow_article_path"
        policy.allowed_paths = ["https://en.wikipedia.org/wiki/*"]
        policy.required_user_agent = True
        policy.max_requests_per_minute = min(60, get_settings().source_requests_per_minute)
        policy.max_concurrency = 1
        policy.decision = "allowed"
        policy.decision_notes = (
            "Ordinary /wiki/{article} paths were checked against live robots.txt; "
            f"robots SHA-256 {robots_sha256}. Generic /w/api.php remains disabled."
        )
        policy.policy_revision = f"robots-sha256:{robots_sha256}"
        policy.reviewed_at = datetime.now(timezone.utc)
    return policy


def page_lookup(title: str) -> dict[str, Any] | None:
    """Refuse API search; ingestion requires an already-resolved enwiki sitelink."""
    raise RawWikipediaError(
        "Wikipedia API title lookup is disabled by current robots.txt; resolve the film "
        "identity and English Wikipedia sitelink before article capture."
    )


def revision_payload(title: str) -> dict[str, Any] | None:
    """Refuse the retired legacy revision lookup path instead of using /w/."""
    raise RawWikipediaError(
        "Wikipedia Action API revision retrieval is disabled by current robots.txt; "
        "use the robots-compliant article-page capture adapter."
    )


def extract_page_assertions(db: Session, snapshot_id, document: ArticleDocument) -> int:
    metadata = document.metadata
    values = [
        ("mediawiki:pageid", {"pageid": metadata.page_id}),
        ("mediawiki:title", {"title": metadata.title}),
        ("wikidata_item", {"wikidata_id": metadata.wikidata_id}),
        ("mediawiki:revisionid", {"revision_id": metadata.revision_id}),
        ("mediawiki:sections", {"sections": list(dict.fromkeys(
            (passage.section_locator, passage.section_title) for passage in document.passages
        ))}),
    ]
    inserted = 0
    for key, value in values:
        if value and all(item is not None for item in value.values()) and source_assertion(
            db, source_snapshot_id=snapshot_id, statement_locator=key, source_property=key,
            raw_subject={"pageid": metadata.page_id, "title": metadata.title}, raw_value=value,
            raw_qualifiers={}, source_rank=None, extractor_version=ADAPTER_VERSION,
        ):
            inserted += 1
    return inserted


def persist_article_snapshot(
    db: Session, *, source: DataSource, run: RawIngestionRun,
    payload: bytes, document: ArticleDocument, media_type: str,
    storage_root: str | Path | None = None,
) -> tuple[SourceSnapshot, bool, int]:
    """Retain exact HTML bytes and append source-shaped page metadata assertions."""
    canonical_url = document.metadata.canonical_url
    item = source_object(
        db, source=source, external_id=f"enwiki:{document.metadata.page_id}",
        object_kind="wiki_page", canonical_url=canonical_url,
    )
    stored, created = snapshot(
        db, item=item, run=run, payload=payload,
        source_revision=str(document.metadata.revision_id),
        canonical_url=canonical_url, license="CC BY-SA 4.0",
        attribution_url=canonical_url, media_type=media_type,
        parser_version=ADAPTER_VERSION, storage_suffix=".html", storage_root=storage_root,
    )
    inserted = extract_page_assertions(db, stored.id, document)
    return stored, created, inserted


def ingest_captured_article(
    db: Session, *, payload: bytes, canonical_url: str, media_type: str,
    expected_qid: str, robots_sha256: str, manifest_uri: str | None = None,
    manifest_sha256: str | None = None,
    storage_root: str | Path | None = None,
) -> dict[str, int]:
    """Persist an already robots-checked exact article response without refetching it."""
    validate_article_capture_hashes(robots_sha256=robots_sha256, manifest_sha256=manifest_sha256)
    source = source_for_wikipedia(db)
    policy = wikipedia_article_html_policy(db, source, robots_sha256=robots_sha256)
    document = parse_article_html(payload, canonical_url=canonical_url,
                                  expected_qid=expected_qid)
    run = RawIngestionRun(
        source_id=source.id, access_policy_id=policy.id,
        adapter_name="wikipedia_article_html_snapshot", adapter_version=ADAPTER_VERSION,
        manifest_uri=manifest_uri, manifest_hash=manifest_sha256,
        status="running", records_requested=1,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    try:
        stored, created, assertions_created = persist_article_snapshot(
            db, source=source, run=run, payload=payload, document=document,
            media_type=media_type, storage_root=storage_root,
        )
        run.records_snapshotted = int(created)
        run.status = "complete"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"resolved": 1, "not_found": 0, "needs_resolution": 0,
                "snapshots": int(created), "source_assertions": assertions_created,
                "page_id": int(stored.source_object.external_id.removeprefix("enwiki:"))}
    except Exception as exc:
        db.rollback()
        failed = db.get(RawIngestionRun, run.id)
        if failed:
            failed.status = "failed"
            failed.error_summary = f"{type(exc).__name__}: {exc}"[:1000]
            failed.records_failed = 1
            failed.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise


def ingest_title_year_entries(db: Session, entries: list[dict[str, Any]], manifest_uri: str | None = None) -> dict[str, int]:
    source = source_for_wikipedia(db)
    stats = {"resolved": 0, "not_found": 0, "needs_resolution": 0,
             "snapshots": 0, "source_assertions": 0}
    if not entries:
        return stats
    settings = get_settings()
    with WikipediaArticleFetcher(
        user_agent=settings.wikidata_user_agent,
        interval_seconds=max(1.0, settings.source_request_interval_seconds),
    ) as fetcher:
        policy = wikipedia_article_html_policy(db, source, robots_sha256=fetcher.robots_sha256 or "unknown")
        run = RawIngestionRun(
            source_id=source.id, access_policy_id=policy.id, adapter_name="wikipedia_article_html_snapshot",
            adapter_version=ADAPTER_VERSION, manifest_uri=manifest_uri, status="running",
            records_requested=len(entries), started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        try:
            for entry in entries:
                qid = str(entry.get("wikidata_id") or "").strip()
                title = str(entry.get("wikipedia_title") or "").strip()
                if not qid or not title:
                    stats["needs_resolution"] += 1
                    run.records_snapshotted = stats["snapshots"]
                    run.records_failed = stats["not_found"] + stats["needs_resolution"]
                    db.commit()
                    continue
                requested_url = article_url(title)
                try:
                    payload, canonical_url, _, media_type = fetcher.fetch(requested_url)
                except FileNotFoundError:
                    stats["not_found"] += 1
                    run.records_snapshotted = stats["snapshots"]
                    run.records_failed = stats["not_found"] + stats["needs_resolution"]
                    db.commit()
                    continue
                document = parse_article_html(
                    payload, canonical_url=canonical_url, expected_qid=qid,
                )
                _, created, assertions_created = persist_article_snapshot(
                    db, source=source, run=run, payload=payload,
                    document=document, media_type=media_type,
                )
                # Commit each film atomically. A stop or restart must not lose
                # earlier captures while the content-addressed files survive.
                run.records_snapshotted = stats["snapshots"] + int(created)
                run.records_failed = stats["not_found"] + stats["needs_resolution"]
                db.flush()
                db.commit()
                stats["resolved"] += 1
                if created:
                    stats["snapshots"] += 1
                stats["source_assertions"] += assertions_created
            run.records_snapshotted = stats["snapshots"]
            run.records_failed = stats["not_found"] + stats["needs_resolution"]
            run.status = "complete"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            failed_run = db.get(RawIngestionRun, run.id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.error_summary = f"{type(exc).__name__}: {exc}"[:1000]
                failed_run.records_snapshotted = stats["snapshots"]
                failed_run.records_failed = len(entries) - stats["resolved"]
                failed_run.completed_at = datetime.now(timezone.utc)
                db.commit()
            raise
    return stats


def read_manifest(path: Path, limit: int | None = None) -> tuple[list[dict[str, Any]], str]:
    payload = path.read_bytes()
    document = json.loads(payload)
    if document.get("schema") != "cinegraph.user-selection-manifest/v1":
        raise RawWikipediaError("This adapter requires a CineGraph user title/year selection manifest.")
    entries = document.get("entries", [])
    if not isinstance(entries, list) or any(not isinstance(item, dict) or "title" not in item for item in entries):
        raise RawWikipediaError("The selection manifest contains invalid entries.")
    return entries[:limit] if limit else entries, hashlib.sha256(payload).hexdigest()


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Capture selected English Wikipedia article pages through robots-allowed /wiki/ routes.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    entries, manifest_hash = read_manifest(args.manifest, limit=args.limit)
    run_migrations()
    with SessionLocal() as db:
        result = ingest_title_year_entries(db, entries, manifest_uri=args.manifest.resolve().as_uri())
        latest = db.scalar(select(RawIngestionRun).where(
            RawIngestionRun.adapter_version == ADAPTER_VERSION,
            RawIngestionRun.manifest_uri == args.manifest.resolve().as_uri(),
        ).order_by(RawIngestionRun.created_at.desc()))
        if latest:
            latest.manifest_hash = manifest_hash
            db.commit()
        print({**result, "manifest_sha256": manifest_hash})


if __name__ == "__main__":
    main()
