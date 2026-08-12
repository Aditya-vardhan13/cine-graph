"""Build the reproducible English 2000–2025 Reference Shelf from CC0 Wikidata facts.

This is intentionally not an IMDb-derived list and does not claim a quality
rank. It balances the release window year by year, then selects each year's
widely documented films by Wikidata's cross-language sitelink count. The
resulting count is retained as a selection signal, not shown as a score.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CanonicalEntity, ReferenceCollection, ReferenceCollectionMembership
from app.services.backfill_evidence_core import backfill
from app.services.wikidata import (
    SOURCE_REFERENCE,
    WikidataIngestionError,
    _ingest_locked,
    exclusive_ingestion_lock,
    fetch_rows_for_film_ids,
    sparql_query_runner,
)

COLLECTION_CODE = "english-2000-2025-reference-shelf-v1"
SELECTION_VERSION = "wikidata-sitelinks-2026-08"


@dataclass(frozen=True)
class Candidate:
    wikidata_id: str
    sitelink_count: int


def reference_collection_query(year: int, limit: int) -> str:
    return f"""
      SELECT ?film (MAX(?sitelinks) AS ?sitelinkCount) WHERE {{
        ?film wdt:P31 wd:Q11424;
              wdt:P364 wd:Q1860;
              wdt:P577 ?releaseDate;
              wikibase:sitelinks ?sitelinks.
        FILTER(YEAR(?releaseDate) = {year})
      }}
      GROUP BY ?film
      ORDER BY DESC(?sitelinkCount) ?film
      LIMIT {limit}
    """


def fetch_reference_candidates(
    limit: int,
    start_year: int,
    end_year: int,
    run_query: Callable[[str], list[dict[str, Any]]] | None = None,
) -> list[Candidate]:
    if limit < 1 or not (1888 <= start_year <= end_year <= 2100):
        raise WikidataIngestionError("Reference Shelf bounds are invalid.")
    runner = run_query or sparql_query_runner()
    years = list(range(start_year, end_year + 1))
    base, remainder = divmod(limit, len(years))
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for index, year in enumerate(years):
        per_year_limit = base + (1 if index < remainder else 0)
        if per_year_limit == 0:
            continue
        for row in runner(reference_collection_query(year, per_year_limit)):
            film_url = row.get("film", {}).get("value", "")
            qid = film_url.rsplit("/", 1)[-1]
            count = row.get("sitelinkCount", {}).get("value")
            if qid.startswith("Q") and qid[1:].isdigit() and count and count.isdigit() and qid not in seen:
                candidates.append(Candidate(wikidata_id=qid, sitelink_count=int(count)))
                seen.add(qid)
    return candidates


def ensure_collection(db: Session, start_year: int, end_year: int) -> ReferenceCollection:
    collection = db.get(ReferenceCollection, COLLECTION_CODE)
    if collection:
        return collection
    collection = ReferenceCollection(
        code=COLLECTION_CODE,
        title="English 2000–2025 Reference Shelf",
        description=(
            "A reproducible, broad English-language film reference collection for CineGraph. "
            "Inclusion is balanced across the release period, English original language, and Wikidata sitelink coverage; "
            "it is not an IMDb list, rating, or quality ranking."
        ),
        language_code="en",
        period_start_year=start_year,
        period_end_year=end_year,
        selection_method="Year-balanced Wikidata English-language release window ordered by sitelink coverage",
        selection_version=SELECTION_VERSION,
    )
    db.add(collection)
    db.flush()
    return collection


def ingest_reference_shelf(
    db: Session,
    *,
    limit: int = 1000,
    start_year: int = 2000,
    end_year: int = 2025,
    candidates: list[Candidate] | None = None,
    rows: list[dict] | None = None,
) -> dict[str, int]:
    """Select, import, evidence-backfill, then register collection membership.

    The one lock covers selection and import. This prevents two local workers
    from assigning incompatible positions or racing an otherwise idempotent
    projection import.
    """
    with exclusive_ingestion_lock():
        selected = candidates if candidates is not None else fetch_reference_candidates(limit, start_year, end_year)
        if not selected:
            raise WikidataIngestionError("Wikidata returned no Reference Shelf candidates; no partial collection was created.")
        ids = [candidate.wikidata_id for candidate in selected]
        imported_rows = rows if rows is not None else fetch_rows_for_film_ids(ids)
        batch = _ingest_locked(
            db,
            limit=len(ids),
            offset=0,
            rows=imported_rows,
            external_reference=(
                f"{SOURCE_REFERENCE}#english-reference-shelf"
                f"?start_year={start_year}&end_year={end_year}&limit={limit}&version={SELECTION_VERSION}"
            ),
        )
        backfill_stats = backfill(db)
        collection = ensure_collection(db, start_year, end_year)
        entities = {
            entity.wikidata_id: entity
            for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.in_(ids)))
        }
        existing = {
            membership.entity_id
            for membership in db.scalars(select(ReferenceCollectionMembership).where(
                ReferenceCollectionMembership.collection_code == collection.code
            ))
        }
        memberships = 0
        for position, candidate in enumerate(selected, start=1):
            entity = entities.get(candidate.wikidata_id)
            if not entity or entity.id in existing:
                continue
            db.add(ReferenceCollectionMembership(
                collection_code=collection.code,
                entity_id=entity.id,
                selection_position=position,
                selection_signals={"wikidata_sitelink_count": candidate.sitelink_count},
                source_reference=SOURCE_REFERENCE,
            ))
            memberships += 1
        db.commit()
        return {
            "selected": len(selected),
            "imported": batch.records_published,
            "memberships_created": memberships,
            **{f"backfill_{key}": value for key, value in backfill_stats.items()},
        }


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Build the CC0 English 2000–2025 CineGraph Reference Shelf.")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2025)
    args = parser.parse_args()
    run_migrations()
    with SessionLocal() as db:
        print(ingest_reference_shelf(
            db, limit=args.limit, start_year=args.start_year, end_year=args.end_year,
        ))


if __name__ == "__main__":
    main()
