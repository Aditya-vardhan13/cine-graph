"""Build a conservative, review-only scholarly-criticism discovery queue.

OpenAlex supplies CC0 *metadata*, not a licence to reuse a discovered paper.
This adapter snapshots only that metadata, then creates title-matched leads for
editorial review. It never downloads a paper, PDF, image, transcript, or video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

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
    NarrativePassage,
    ReferenceCollection,
    RawIngestionRun,
    ReferenceCollectionMembership,
    SourceAccessPolicy,
)
from app.services.raw_snapshots import source_assertion, source_object, snapshot


OPENALEX_WORKS_API = "https://api.openalex.org/works"
OPENALEX_SOURCE_URL = "https://openalex.org/"
PROVIDER = "openalex"
QUERY_VERSION = "openalex-title-phrase-v1"
ADAPTER_VERSION = "openalex-critical-discovery-v1"
DEFAULT_COLLECTION = "english-1000-retained-narrative-v1"
WORD = re.compile(r"[a-z0-9]+")
AMBIGUOUS_TITLES = {"her", "up", "it", "us", "m", "pi", "life", "glory", "crash", "drive", "heat", "room"}


class OpenAlexDiscoveryError(RuntimeError):
    pass


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(WORD.findall(folded.lower()))


def is_safe_title_query(title: str) -> bool:
    normalized = normalize(title)
    tokens = normalized.split()
    return len(normalized) >= 8 and (len(tokens) >= 2 or normalized not in AMBIGUOUS_TITLES)


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    words = {position: word for word, positions in inverted_index.items() for position in positions}
    return " ".join(words[position] for position in sorted(words))


def work_title_match(title: str, work: dict[str, Any]) -> tuple[str, float] | None:
    """Return only conservative, inspectable title/abstract phrase matches."""
    phrase = normalize(title)
    candidate_title = normalize(str(work.get("title") or ""))
    abstract = normalize(reconstruct_abstract(work.get("abstract_inverted_index")))
    if phrase not in candidate_title and phrase not in abstract:
        return None
    if phrase in candidate_title and phrase in abstract:
        return "title_and_abstract_phrase", 1.0
    if phrase in candidate_title:
        return "title_phrase", 0.92
    return "title_and_abstract_phrase", 0.80


def source_for_openalex(db: Session) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == "OpenAlex"))
    if source is not None:
        return source
    source = DataSource(
        name="OpenAlex",
        url=OPENALEX_SOURCE_URL,
        source_type="scholarly_discovery_metadata",
        license="CC0 metadata",
        rights_status="metadata_link_only",
        notes="OpenAlex is a CC0 scholarly metadata discovery layer. Linked work text requires separate licence verification.",
    )
    db.add(source)
    db.flush()
    return source


def openalex_api_policy(db: Session, source: DataSource) -> SourceAccessPolicy:
    policy = db.scalar(select(SourceAccessPolicy).where(
        SourceAccessPolicy.source_id == source.id,
        SourceAccessPolicy.access_mode == "api",
    ))
    if policy is not None:
        policy.max_requests_per_minute = get_settings().openalex_requests_per_minute
        return policy
    policy = SourceAccessPolicy(
        source_id=source.id,
        access_mode="api",
        policy_url="https://help.openalex.org/hc/en-us/articles/24397762024087-Pricing",
        robots_url="https://api.openalex.org/robots.txt",
        robots_decision="documented_api_route",
        allowed_paths=[OPENALEX_WORKS_API],
        required_user_agent=True,
        max_requests_per_minute=get_settings().openalex_requests_per_minute,
        max_concurrency=1,
        decision="allowed",
        decision_notes=(
            "CC0 metadata only, documented API route, identifying user agent, sequential pacing, and stop-on-denial/rate-limit. "
            "Free API allowance is 100k calls/day and 10/second; observed network behaviour takes priority, so this adapter uses its own slower configurable pace."
        ),
    )
    db.add(policy)
    db.flush()
    return policy


def collection_entities(db: Session, collection_code: str) -> list[CanonicalEntity]:
    if collection_code == DEFAULT_COLLECTION:
        ensure_retained_narrative_collection(db)
    entities = list(db.scalars(
        select(CanonicalEntity)
        .join(ReferenceCollectionMembership, ReferenceCollectionMembership.entity_id == CanonicalEntity.id)
        .where(ReferenceCollectionMembership.collection_code == collection_code)
        .order_by(ReferenceCollectionMembership.selection_position)
    ))
    if not entities:
        raise OpenAlexDiscoveryError(f"No entities found in reference collection {collection_code!r}.")
    return entities


def ensure_retained_narrative_collection(db: Session) -> ReferenceCollection:
    """Freeze the current exact English-1,000 narrative corpus as a discovery target.

    The local catalog was assembled before reference-collection memberships were
    retained. The 24,446 attributable narrative passages are, however, already
    an exact, auditable 1,000-film boundary. This recovery collection makes the
    boundary explicit once; it never silently absorbs later passages.
    """
    collection = db.get(ReferenceCollection, DEFAULT_COLLECTION)
    if collection is not None:
        return collection
    entity_ids = list(db.scalars(select(NarrativePassage.subject_entity_id).distinct()))
    entities = list(db.scalars(select(CanonicalEntity).where(
        CanonicalEntity.id.in_(entity_ids),
        CanonicalEntity.entity_kind == "film",
    ).order_by(CanonicalEntity.canonical_label)))
    if len(entities) != 1000:
        raise OpenAlexDiscoveryError(
            f"Retained narrative recovery expects exactly 1,000 films, found {len(entities)}; refusing to infer a target set."
        )
    collection = ReferenceCollection(
        code=DEFAULT_COLLECTION,
        title="English-1,000 Retained Narrative Discovery Target",
        description=(
            "Frozen recovery collection of the 1,000 distinct film entities with retained, attributable English Wikipedia "
            "narrative passages at the time scholarly-discovery preparation began. It is a corpus boundary, not a rank."
        ),
        language_code="en",
        selection_method="Exact distinct entities in retained English narrative-passage corpus",
        selection_version="retained-narrative-1000-2026-08",
    )
    db.add(collection)
    db.flush()
    for position, entity in enumerate(entities, start=1):
        db.add(ReferenceCollectionMembership(
            collection_code=collection.code,
            entity_id=entity.id,
            selection_position=position,
            selection_signals={"narrative_passage_boundary": True},
            source_reference="CineGraph retained, attributable English narrative passage corpus",
        ))
    db.commit()
    return collection


def pending_entities(
    db: Session,
    entities: Iterable[CanonicalEntity],
    *,
    provider: str = PROVIDER,
    query_version: str = QUERY_VERSION,
) -> list[CanonicalEntity]:
    checked_ids = set(db.scalars(select(CriticalDiscoveryQuery.subject_entity_id).where(
        CriticalDiscoveryQuery.provider == provider,
        CriticalDiscoveryQuery.query_version == query_version,
        CriticalDiscoveryQuery.status.in_(("complete", "no_candidates", "skipped_ambiguous")),
    )))
    return [entity for entity in entities if entity.id not in checked_ids]


def fetch_works(client: httpx.Client, title: str) -> list[dict[str, Any]]:
    response = client.get(OPENALEX_WORKS_API, params={
        "search": f'"{title}"',
        "per-page": 10,
        "select": (
            "id,title,doi,publication_date,authorships,primary_location,best_oa_location,"
            "open_access,language,cited_by_count,type,abstract_inverted_index"
        ),
    })
    if response.status_code in {401, 403}:
        raise OpenAlexDiscoveryError(f"OpenAlex denied the request ({response.status_code}); stopping.")
    if response.status_code == 429:
        retry_after = getattr(response, "headers", {}).get("Retry-After")
        suffix = f" Retry-After: {retry_after}." if retry_after else ""
        raise OpenAlexDiscoveryError(f"OpenAlex rate-limited the run; stopping without retries.{suffix}")
    response.raise_for_status()
    results = response.json().get("results", [])
    return [result for result in results if isinstance(result, dict)]


def work_id(work: dict[str, Any]) -> str:
    raw = str(work.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
    if not raw.startswith("W"):
        raise OpenAlexDiscoveryError("OpenAlex work has no stable W identifier.")
    return raw


def work_url(work: dict[str, Any]) -> str:
    return str(work.get("id") or f"{OPENALEX_SOURCE_URL}works/{work_id(work)}")


def compact_metadata(work: dict[str, Any]) -> dict[str, Any]:
    location = work.get("best_oa_location") or work.get("primary_location") or {}
    oa = work.get("open_access") or {}
    return {
        "doi": work.get("doi"),
        "publication_date": work.get("publication_date"),
        "authors": [
            item.get("author", {}).get("display_name")
            for item in (work.get("authorships") or [])
            if item.get("author", {}).get("display_name")
        ],
        "language": work.get("language"),
        "type": work.get("type"),
        "cited_by_count": work.get("cited_by_count"),
        "open_access": {
            "is_oa": oa.get("is_oa"),
            "oa_status": oa.get("oa_status"),
            "license": location.get("license"),
            "landing_page_url": location.get("landing_page_url"),
            "pdf_url": location.get("pdf_url"),
        },
    }


def snapshot_work(db: Session, *, source: DataSource, run: RawIngestionRun, work: dict[str, Any]) -> tuple[Any, bool]:
    identifier = work_id(work)
    url = work_url(work)
    item = source_object(db, source=source, external_id=f"openalex:{identifier}", object_kind="scholarly_work_metadata", canonical_url=url)
    payload = json.dumps(work, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    stored, created = snapshot(
        db,
        item=item,
        run=run,
        payload=payload,
        source_revision=hashlib.sha256(payload).hexdigest(),
        canonical_url=url,
        license="CC0 1.0",
        attribution_url=url,
        parser_version=ADAPTER_VERSION,
    )
    if created:
        source_assertion(
            db,
            source_snapshot_id=stored.id,
            statement_locator="openalex:work_metadata",
            source_property="openalex:work_metadata",
            raw_subject={"openalex_id": identifier},
            raw_value=compact_metadata(work),
            raw_qualifiers={},
            source_rank=None,
            extractor_version=ADAPTER_VERSION,
        )
    return stored, created


def upsert_query(
    db: Session,
    *,
    entity: CanonicalEntity,
    run: RawIngestionRun,
    status: str,
    candidates_found: int,
    provider: str = PROVIDER,
    query_version: str = QUERY_VERSION,
    error_summary: str | None = None,
) -> None:
    query = db.scalar(select(CriticalDiscoveryQuery).where(
        CriticalDiscoveryQuery.subject_entity_id == entity.id,
        CriticalDiscoveryQuery.provider == provider,
        CriticalDiscoveryQuery.query_version == query_version,
    ))
    if query is None:
        db.add(CriticalDiscoveryQuery(
            subject_entity_id=entity.id,
            ingestion_run_id=run.id,
            provider=provider,
            query_version=query_version,
            query_title=entity.canonical_label,
            status=status,
            candidates_found=candidates_found,
            error_summary=error_summary,
            checked_at=datetime.now(timezone.utc),
        ))
        return
    query.ingestion_run_id = run.id
    query.status = status
    query.candidates_found = candidates_found
    query.error_summary = error_summary
    query.checked_at = datetime.now(timezone.utc)


def discover(
    db: Session,
    *,
    collection_code: str = DEFAULT_COLLECTION,
    limit: int | None = None,
    progress_every: int = 25,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    source = source_for_openalex(db)
    policy = openalex_api_policy(db, source)
    if policy.decision != "allowed":
        raise OpenAlexDiscoveryError("The OpenAlex API policy is not approved; refusing to fetch.")
    entities = pending_entities(db, collection_entities(db, collection_code))
    if limit is not None:
        entities = entities[:limit]
    run = RawIngestionRun(
        source_id=source.id,
        access_policy_id=policy.id,
        adapter_name="openalex_critical_discovery",
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
    stats = {"queried": 0, "skipped_ambiguous": 0, "no_candidates": 0, "candidates": 0, "snapshots": 0}
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=60,
        headers={"User-Agent": get_settings().wikidata_user_agent, "Accept-Encoding": "gzip, deflate"},
    )
    try:
        for position, entity in enumerate(entities, start=1):
            title = entity.canonical_label
            if not is_safe_title_query(title):
                upsert_query(db, entity=entity, run=run, status="skipped_ambiguous", candidates_found=0)
                stats["skipped_ambiguous"] += 1
            else:
                works = fetch_works(http_client, title)
                stats["queried"] += 1
                accepted = 0
                for work in works:
                    match = work_title_match(title, work)
                    if match is None:
                        continue
                    stored_snapshot, created_snapshot = snapshot_work(db, source=source, run=run, work=work)
                    if created_snapshot:
                        stats["snapshots"] += 1
                    method, score = match
                    identifier = work_id(work)
                    candidate = db.scalar(select(CriticalDiscoveryCandidate).where(
                        CriticalDiscoveryCandidate.subject_entity_id == entity.id,
                        CriticalDiscoveryCandidate.provider == PROVIDER,
                        CriticalDiscoveryCandidate.provider_work_id == identifier,
                    ))
                    if candidate is None:
                        db.add(CriticalDiscoveryCandidate(
                            subject_entity_id=entity.id,
                            source_snapshot_id=stored_snapshot.id,
                            provider=PROVIDER,
                            provider_work_id=identifier,
                            query_title=title,
                            candidate_title=str(work.get("title") or identifier),
                            candidate_url=work_url(work),
                            match_method=method,
                            match_score=score,
                            metadata_json=compact_metadata(work),
                        ))
                        accepted += 1
                upsert_query(
                    db,
                    entity=entity,
                    run=run,
                    status="complete" if accepted else "no_candidates",
                    candidates_found=accepted,
                )
                if not accepted:
                    stats["no_candidates"] += 1
                stats["candidates"] += accepted
                if position < len(entities):
                    time.sleep(get_settings().openalex_request_interval_seconds)
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
        # Preserve a terminal, auditable run record even after a batch-flush
        # failure, when the current transaction is otherwise unusable.
        db.rollback()
        run.status = "failed"
        run.error_summary = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
    finally:
        if owns_client:
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

    parser = argparse.ArgumentParser(description="Discover scholarly criticism metadata for a vetted CineGraph collection.")
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
