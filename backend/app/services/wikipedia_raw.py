"""Compliant, revisioned English Wikipedia enrichment for selected title/year records.

``wikipedia-api`` resolves pages and their section structure. A documented
MediaWiki API request then captures the exact wikitext revision for an
immutable, attributable snapshot. This is deliberately a bounded-pilot
adapter; bulk 100k work must use Wikimedia dumps.
"""
from __future__ import annotations

import json
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx
import wikipediaapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DataSource, RawIngestionRun, SourceAccessPolicy
from app.services.raw_snapshots import source_assertion, source_object, snapshot

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
SOURCE_URL = "https://en.wikipedia.org/"
SOURCE_NAME = "English Wikipedia"
ADAPTER_VERSION = "enwiki-revision-snapshot-v1"
MIN_REQUEST_INTERVAL_SECONDS = 1.0


class RawWikipediaError(RuntimeError):
    pass


def source_for_wikipedia(db: Session) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if source:
        return source
    source = DataSource(
        name=SOURCE_NAME,
        url=SOURCE_URL,
        source_type="revisioned_narrative_context",
        license="CC BY-SA 4.0",
        rights_status="attributed_reuse",
        notes="English Wikipedia revisions are retained only as separately attributed CC BY-SA source snapshots. No HTML crawling.",
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
        return policy
    policy = SourceAccessPolicy(
        source_id=source.id,
        access_mode="api",
        policy_url="https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy",
        robots_url="https://en.wikipedia.org/robots.txt",
        robots_decision="documented_api_route",
        allowed_paths=[WIKIPEDIA_API],
        required_user_agent=True,
        max_requests_per_minute=60,
        max_concurrency=1,
        decision="allowed",
        decision_notes="Bounded pilot through documented MediaWiki API with meaningful user agent, sequential pacing, revision attribution and stop-on-denial policy.",
    )
    db.add(policy)
    db.flush()
    return policy


def page_lookup(title: str) -> dict[str, Any] | None:
    """Resolve a title via wikipedia-api before asking MediaWiki for its revision."""
    wiki = wikipediaapi.Wikipedia(
        user_agent=get_settings().wikidata_user_agent,
        language="en",
        extract_format=wikipediaapi.ExtractFormat.WIKI,
    )
    page = wiki.page(title)
    if not page.exists():
        return None
    return {
        "requested_title": title,
        "resolved_title": page.title,
        "pageid": page.pageid,
        "fullurl": page.fullurl,
        "section_titles": [section.title for section in page.sections],
    }


def revision_payload(title: str) -> dict[str, Any] | None:
    headers = {"User-Agent": get_settings().wikidata_user_agent, "Accept-Encoding": "gzip, deflate"}
    with httpx.Client(timeout=60, headers=headers) as client:
        response = client.get(WIKIPEDIA_API, params={
            "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
            "titles": title, "prop": "pageprops|revisions", "ppprop": "wikibase_item",
            "rvprop": "ids|timestamp|content|contentmodel", "rvslots": "main", "maxlag": "5",
        })
    if response.status_code in {401, 403}:
        raise RawWikipediaError(f"Wikipedia denied the request ({response.status_code}); stopping.")
    if response.status_code == 429:
        raise RawWikipediaError("Wikipedia rate-limited the run; stop and retry after the supplied delay.")
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", [])
    return pages[0] if pages and "missing" not in pages[0] else None


def extract_page_assertions(db: Session, snapshot_id, page: dict[str, Any], lookup: dict[str, Any]) -> int:
    values = [
        ("mediawiki:pageid", {"pageid": page.get("pageid")}),
        ("mediawiki:title", {"title": page.get("title")}),
        ("wikidata_item", {"wikidata_id": page.get("pageprops", {}).get("wikibase_item")}),
        ("mediawiki:sections", {"section_titles": lookup["section_titles"]}),
    ]
    inserted = 0
    for key, value in values:
        if value and all(item is not None for item in value.values()) and source_assertion(
            db, source_snapshot_id=snapshot_id, statement_locator=key, source_property=key,
            raw_subject={"pageid": page.get("pageid"), "title": page.get("title")}, raw_value=value,
            raw_qualifiers={}, source_rank=None, extractor_version=ADAPTER_VERSION,
        ):
            inserted += 1
    return inserted


def ingest_title_year_entries(db: Session, entries: list[dict[str, Any]], manifest_uri: str | None = None) -> dict[str, int]:
    source = source_for_wikipedia(db)
    policy = wikipedia_api_policy(db, source)
    if policy.decision != "allowed":
        raise RawWikipediaError("The registered Wikipedia API policy is not approved; refusing to fetch.")
    run = RawIngestionRun(
        source_id=source.id, access_policy_id=policy.id, adapter_name="wikipedia_api_revision_snapshot",
        adapter_version=ADAPTER_VERSION, manifest_uri=manifest_uri, status="running",
        records_requested=len(entries), started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    db.commit()
    stats = {"resolved": 0, "not_found": 0, "snapshots": 0, "source_assertions": 0}
    for index, entry in enumerate(entries):
        title = str(entry.get("wikipedia_title") or entry["title"])
        lookup = page_lookup(title)
        time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
        if not lookup:
            stats["not_found"] += 1
            continue
        page = revision_payload(lookup["resolved_title"])
        if not page:
            stats["not_found"] += 1
            continue
        expected_qid = entry.get("wikidata_id")
        actual_qid = page.get("pageprops", {}).get("wikibase_item")
        if expected_qid and actual_qid != expected_qid:
            stats["not_found"] += 1
            continue
        stats["resolved"] += 1
        revision = (page.get("revisions") or [{}])[0]
        source_revision = str(revision.get("revid")) if revision.get("revid") else None
        canonical_url = lookup["fullurl"]
        item = source_object(
            db, source=source, external_id=f"enwiki:{page['pageid']}", object_kind="wiki_page", canonical_url=canonical_url,
        )
        payload = json.dumps({"page": page, "lookup": lookup, "manifest_entry": entry}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        stored, created = snapshot(
            db, item=item, run=run, payload=payload, source_revision=source_revision,
            canonical_url=canonical_url, license="CC BY-SA 4.0", attribution_url=canonical_url,
            media_type="application/json", parser_version=ADAPTER_VERSION,
        )
        if created:
            stats["snapshots"] += 1
            stats["source_assertions"] += extract_page_assertions(db, stored.id, page, lookup)
        if (index + 1) % 25 == 0:
            run.records_snapshotted = stats["snapshots"]
            run.records_failed = stats["not_found"]
            db.commit()
        if index + 1 < len(entries):
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
    run.records_snapshotted = stats["snapshots"]
    run.records_failed = stats["not_found"]
    run.status = "complete"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
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

    parser = argparse.ArgumentParser(description="Snapshot selected English Wikipedia revisions through wikipedia-api and MediaWiki API.")
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
