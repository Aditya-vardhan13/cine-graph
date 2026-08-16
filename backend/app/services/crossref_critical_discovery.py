"""Build a conservative, review-only scholarly-criticism queue from Crossref.

Crossref's API exposes bibliographic metadata. Its documentation cautions that
deposited abstracts can be copyrighted, so this adapter deliberately does not
request, retain, or use abstracts. A result is only a title-matched lead for a
human reviewer; it is neither an admitted critical work nor a CineGraph fact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import (
    CanonicalEntity,
    CriticalDiscoveryCandidate,
    CriticalDiscoveryQuery,
    DataSource,
    RawIngestionRun,
    SourceAccessPolicy,
)
from app.services.openalex_critical_discovery import (
    DEFAULT_COLLECTION,
    collection_entities,
    is_safe_title_query,
    normalize,
    pending_entities,
    upsert_query,
)
from app.services.raw_snapshots import source_assertion, source_object, snapshot


CROSSREF_WORKS_API = "https://api.crossref.org/works"
CROSSREF_SOURCE_URL = "https://www.crossref.org/documentation/retrieve-metadata/rest-api/"
PROVIDER = "crossref"
QUERY_VERSION = "crossref-title-phrase-v1"
ADAPTER_VERSION = "crossref-critical-discovery-v1"


class CrossrefDiscoveryError(RuntimeError):
    pass


def source_for_crossref(db: Session) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == "Crossref"))
    if source is not None:
        return source
    source = DataSource(
        name="Crossref",
        url=CROSSREF_SOURCE_URL,
        source_type="scholarly_discovery_metadata",
        license="CC0-like bibliographic metadata; individual work rights separate",
        rights_status="metadata_link_only",
        notes=(
            "Crossref discovery snapshots bibliographic metadata only. Abstracts, linked files, and work-level licence "
            "claims are not retained by this adapter and require separate review."
        ),
    )
    db.add(source)
    db.flush()
    return source


def crossref_api_policy(db: Session, source: DataSource) -> SourceAccessPolicy:
    policy = db.scalar(select(SourceAccessPolicy).where(
        SourceAccessPolicy.source_id == source.id,
        SourceAccessPolicy.access_mode == "api",
    ))
    if policy is not None:
        policy.max_requests_per_minute = get_settings().crossref_requests_per_minute
        return policy
    policy = SourceAccessPolicy(
        source_id=source.id,
        access_mode="api",
        policy_url=CROSSREF_SOURCE_URL,
        robots_url="https://api.crossref.org/robots.txt",
        robots_decision="documented_api_route",
        allowed_paths=[CROSSREF_WORKS_API],
        required_user_agent=True,
        max_requests_per_minute=get_settings().crossref_requests_per_minute,
        max_concurrency=1,
        decision="allowed",
        decision_notes=(
            "Documented REST API using the public pool, sequentially at 30 requests per minute (below the documented "
            "one list-query-per-second public limit), identifying user agent, and hard stop on denial or 429. "
            "A valid contact email may be configured later for Crossref's polite pool, but is not assumed."
        ),
    )
    db.add(policy)
    db.flush()
    return policy


def safe_work(record: dict[str, Any]) -> dict[str, Any] | None:
    """Drop abstract and all non-bibliographic response material before it can persist."""
    doi = str(record.get("DOI") or "").strip().lower()
    titles = record.get("title") or []
    title = str(titles[0]).strip() if titles else ""
    if not doi or not title:
        return None
    return {
        "DOI": doi,
        "title": title,
        "URL": str(record.get("URL") or f"https://doi.org/{doi}"),
        "type": record.get("type"),
        "published": record.get("published"),
        "published_print": record.get("published-print"),
        "published_online": record.get("published-online"),
        "author": record.get("author") or [],
        "container_title": record.get("container-title") or [],
        "publisher": record.get("publisher"),
        "license": record.get("license") or [],
        "is_referenced_by_count": record.get("is-referenced-by-count"),
    }


def fetch_works(client: httpx.Client, title: str) -> list[dict[str, Any]]:
    response = client.get(CROSSREF_WORKS_API, params={"query.bibliographic": title, "rows": 20})
    if response.status_code in {401, 403}:
        raise CrossrefDiscoveryError(f"Crossref denied the request ({response.status_code}); stopping.")
    if response.status_code == 429:
        retry_after = getattr(response, "headers", {}).get("Retry-After")
        suffix = f" Retry-After: {retry_after}." if retry_after else ""
        raise CrossrefDiscoveryError(f"Crossref rate-limited the run; stopping without retries.{suffix}")
    response.raise_for_status()
    items = response.json().get("message", {}).get("items", [])
    return [work for item in items if isinstance(item, dict) and (work := safe_work(item)) is not None]


def title_match(title: str, work: dict[str, Any]) -> tuple[str, float] | None:
    expected = normalize(title)
    candidate = normalize(str(work["title"]))
    if expected == candidate:
        return "title_phrase", 1.0
    if expected in candidate:
        return "title_phrase", 0.92
    return None


def compact_metadata(work: dict[str, Any]) -> dict[str, Any]:
    return {
        "doi": work["DOI"],
        "type": work.get("type"),
        "published": work.get("published") or work.get("published_online") or work.get("published_print"),
        "authors": [
            " ".join(part for part in (author.get("given"), author.get("family")) if part)
            for author in work.get("author", [])
            if isinstance(author, dict)
        ],
        "container_title": work.get("container_title"),
        "publisher": work.get("publisher"),
        "license": work.get("license"),
        "is_referenced_by_count": work.get("is_referenced_by_count"),
    }


def snapshot_work(
    db: Session,
    *,
    source: DataSource,
    run: RawIngestionRun,
    work: dict[str, Any],
    storage_root: str | Path | None = None,
) -> tuple[Any, bool]:
    doi = work["DOI"]
    url = str(work["URL"])
    item = source_object(db, source=source, external_id=f"crossref:{doi}", object_kind="scholarly_work_metadata", canonical_url=url)
    payload = json.dumps(work, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    stored, created = snapshot(
        db,
        item=item,
        run=run,
        payload=payload,
        source_revision=hashlib.sha256(payload).hexdigest(),
        canonical_url=url,
        license="CC0 bibliographic metadata; individual work rights unverified",
        attribution_url=url,
        parser_version=ADAPTER_VERSION,
        storage_root=storage_root,
    )
    if created:
        source_assertion(
            db,
            source_snapshot_id=stored.id,
            statement_locator="crossref:work_metadata",
            source_property="crossref:work_metadata",
            raw_subject={"doi": doi},
            raw_value=compact_metadata(work),
            raw_qualifiers={},
            source_rank=None,
            extractor_version=ADAPTER_VERSION,
        )
    return stored, created


def discover(
    db: Session,
    *,
    collection_code: str = DEFAULT_COLLECTION,
    limit: int | None = None,
    progress_every: int = 25,
    client: httpx.Client | None = None,
    work_fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
    storage_root: str | Path | None = None,
    delay_seconds: float | None = None,
) -> dict[str, int]:
    source = source_for_crossref(db)
    policy = crossref_api_policy(db, source)
    if policy.decision != "allowed":
        raise CrossrefDiscoveryError("The Crossref API policy is not approved; refusing to fetch.")
    entities = pending_entities(
        db, collection_entities(db, collection_code), provider=PROVIDER, query_version=QUERY_VERSION
    )
    if limit is not None:
        entities = entities[:limit]
    run = RawIngestionRun(
        source_id=source.id,
        access_policy_id=policy.id,
        adapter_name="crossref_critical_discovery",
        adapter_version=ADAPTER_VERSION,
        manifest_uri=f"collection:{collection_code}",
        input_revision=QUERY_VERSION,
        status="running",
        records_requested=len(entities),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    db.commit()
    stats = {"queried": 0, "skipped_ambiguous": 0, "timeouts": 0, "no_candidates": 0, "candidates": 0, "snapshots": 0}
    owns_client = client is None and work_fetcher is None
    http_client = client or (httpx.Client(
        timeout=60,
        headers={"User-Agent": get_settings().wikidata_user_agent, "Accept-Encoding": "gzip, deflate"},
    ) if work_fetcher is None else None)
    try:
        for position, entity in enumerate(entities, start=1):
            title = entity.canonical_label
            if not is_safe_title_query(title):
                upsert_query(
                    db, entity=entity, run=run, status="skipped_ambiguous", candidates_found=0,
                    provider=PROVIDER, query_version=QUERY_VERSION,
                )
                stats["skipped_ambiguous"] += 1
            else:
                try:
                    works = work_fetcher(title) if work_fetcher is not None else fetch_works(http_client, title)
                except httpx.TimeoutException as exc:
                    # One slow record must not prevent the rest of a bounded,
                    # sequential queue from finishing. Keep this title visibly
                    # failed and eligible for an explicit later resume; do not
                    # retry it in the same run.
                    upsert_query(
                        db, entity=entity, run=run, status="failed", candidates_found=0,
                        error_summary=f"{type(exc).__name__}: {exc}", provider=PROVIDER, query_version=QUERY_VERSION,
                    )
                    stats["timeouts"] += 1
                else:
                    stats["queried"] += 1
                    accepted = 0
                    for work in works:
                        match = title_match(title, work)
                        if match is None:
                            continue
                        stored_snapshot, created_snapshot = snapshot_work(
                            db, source=source, run=run, work=work, storage_root=storage_root,
                        )
                        if created_snapshot:
                            stats["snapshots"] += 1
                        method, score = match
                        candidate = db.scalar(select(CriticalDiscoveryCandidate).where(
                            CriticalDiscoveryCandidate.subject_entity_id == entity.id,
                            CriticalDiscoveryCandidate.provider == PROVIDER,
                            CriticalDiscoveryCandidate.provider_work_id == work["DOI"],
                        ))
                        if candidate is None:
                            db.add(CriticalDiscoveryCandidate(
                                subject_entity_id=entity.id,
                                source_snapshot_id=stored_snapshot.id,
                                provider=PROVIDER,
                                provider_work_id=work["DOI"],
                                query_title=title,
                                candidate_title=work["title"],
                                candidate_url=str(work["URL"]),
                                match_method=method,
                                match_score=score,
                                metadata_json=compact_metadata(work),
                            ))
                            accepted += 1
                    upsert_query(
                        db, entity=entity, run=run, status="complete" if accepted else "no_candidates",
                        candidates_found=accepted, provider=PROVIDER, query_version=QUERY_VERSION,
                    )
                    stats["candidates"] += accepted
                    if not accepted:
                        stats["no_candidates"] += 1
                if position < len(entities):
                    wait = get_settings().crossref_request_interval_seconds if delay_seconds is None else delay_seconds
                    if wait > 0:
                        time.sleep(wait)
            if position % progress_every == 0 or position == len(entities):
                run.records_snapshotted = stats["snapshots"]
                db.commit()
                print(json.dumps({"progress": {"completed": position, "total": len(entities)}, **stats}), flush=True)
        run.records_snapshotted = stats["snapshots"]
        run.status = "complete"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"requested": len(entities), **stats}
    except Exception as exc:
        # A failed flush leaves SQLAlchemy's transaction unusable. Roll back the
        # uncommitted batch, then persist a terminal status for safe resumption.
        db.rollback()
        run.status = "failed"
        run.error_summary = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
    finally:
        if owns_client and http_client is not None:
            http_client.close()


def quality_report(db: Session, collection_code: str = DEFAULT_COLLECTION) -> dict[str, int]:
    entities = collection_entities(db, collection_code)
    entity_ids = [entity.id for entity in entities]
    queries = list(db.scalars(select(CriticalDiscoveryQuery).where(
        CriticalDiscoveryQuery.subject_entity_id.in_(entity_ids),
        CriticalDiscoveryQuery.provider == PROVIDER,
        CriticalDiscoveryQuery.query_version == QUERY_VERSION,
    )))
    candidates = db.scalar(select(func.count()).select_from(CriticalDiscoveryCandidate).where(
        CriticalDiscoveryCandidate.subject_entity_id.in_(entity_ids),
        CriticalDiscoveryCandidate.provider == PROVIDER,
    )) or 0
    statuses = {status: sum(query.status == status for query in queries) for status in ("complete", "no_candidates", "skipped_ambiguous", "failed")}
    return {"collection_films": len(entities), "checked": len(queries), "candidates": candidates, **statuses}


def main() -> None:
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Discover Crossref criticism metadata for a vetted CineGraph collection.")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    if args.progress_every < 1:
        parser.error("--progress-every must be positive")
    run_migrations()
    with SessionLocal() as db:
        if args.quality:
            print(json.dumps(quality_report(db, args.collection), indent=2))
        else:
            print(json.dumps(discover(db, collection_code=args.collection, limit=args.limit, progress_every=args.progress_every), indent=2))


if __name__ == "__main__":
    main()
