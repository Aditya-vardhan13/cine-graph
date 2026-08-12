"""Resolve CMU narrative records to canonical Wikidata films using exact legacy IDs.

No title/year fuzzy matching is used here. A CMU record is linked only when its
Freebase identifier has exactly one direct Wikidata P646 match. The canonical
metadata is then retrieved from that resolved Wikidata item.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CorpusRecord, DataSource, Film
from app.services.cmu_movie_summaries import source_for_cmu
from app.services.wikidata import (
    ENDPOINT,
    _ingest_locked,
    exclusive_ingestion_lock,
    fetch_rows_for_film_ids,
    fetch_wikidata_ids_for_freebase,
    sparql_query_runner,
)


def reconcile_cmu_records(
    db: Session,
    page_size: int = 100,
    limit: int | None = None,
    mapper: Callable[[list[str]], dict[str, set[str]]] | None = None,
    metadata_fetcher: Callable[[list[str]], list[dict]] | None = None,
) -> dict[str, int]:
    """Reconcile all unresolved CMU records, committing each source page.

    ``mapper`` and ``metadata_fetcher`` are injectable to make the exact-ID
    policy testable without contacting Wikidata.
    """
    if page_size < 1:
        raise ValueError("page_size must be positive")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")

    source = source_for_cmu(db)
    db.commit()
    stats = {"seen": 0, "matched": 0, "unmatched": 0, "ambiguous": 0, "canonical_films": 0}
    with exclusive_ingestion_lock():
        runner = sparql_query_runner() if mapper is None or metadata_fetcher is None else None
        while limit is None or stats["seen"] < limit:
            remaining = page_size if limit is None else min(page_size, limit - stats["seen"])
            records = list(db.scalars(select(CorpusRecord).where(
                CorpusRecord.source_id == source.id,
                CorpusRecord.match_status == "unresolved",
            ).order_by(CorpusRecord.external_id).limit(remaining)))
            if not records:
                break

            freebase_by_record = {
                record.id: str(record.raw_metadata.get("freebase_movie_id", ""))
                for record in records
            }
            usable_ids = sorted({freebase_id for freebase_id in freebase_by_record.values() if freebase_id})
            mappings = mapper(usable_ids) if mapper else fetch_wikidata_ids_for_freebase(usable_ids, runner)

            resolved_qids: set[str] = set()
            unique_qid_by_record: dict[object, str] = {}
            for record in records:
                candidates = mappings.get(freebase_by_record[record.id], set())
                if len(candidates) == 1:
                    qid = next(iter(candidates))
                    unique_qid_by_record[record.id] = qid
                    resolved_qids.add(qid)
                elif len(candidates) > 1:
                    record.match_status = "review_required"
                    record.match_method = "wikidata_p646_ambiguous"
                    record.match_confidence = None
                    stats["ambiguous"] += 1
                else:
                    record.match_status = "unmatched_external_id"
                    record.match_method = "wikidata_p646"
                    record.match_confidence = 0.0
                    stats["unmatched"] += 1

            if resolved_qids:
                qids = sorted(resolved_qids)
                rows = metadata_fetcher(qids) if metadata_fetcher else fetch_rows_for_film_ids(qids, runner)
                batch = _ingest_locked(
                    db,
                    limit=len(qids),
                    offset=0,
                    rows=rows,
                    external_reference=f"{ENDPOINT}#CMU-P646-exact-id",
                )
                films_by_qid = {
                    film.wikidata_id: film
                    for film in db.scalars(select(Film).where(Film.wikidata_id.in_(qids)))
                }
                stats["canonical_films"] += batch.records_published
                for record in records:
                    qid = unique_qid_by_record.get(record.id)
                    film = films_by_qid.get(qid) if qid else None
                    if film:
                        record.film_id = film.id
                        record.match_status = "matched"
                        record.match_method = "wikidata_p646_exact"
                        record.match_confidence = 1.0
                        stats["matched"] += 1
                    elif qid:
                        record.match_status = "unmatched_canonical_metadata"
                        record.match_method = "wikidata_p646"
                        record.match_confidence = 0.0
                        stats["unmatched"] += 1

            stats["seen"] += len(records)
            db.commit()
            print(
                "CMU reconciliation checkpoint: "
                f"seen={stats['seen']} matched={stats['matched']} "
                f"unmatched={stats['unmatched']} ambiguous={stats['ambiguous']} "
                f"canonical_films={stats['canonical_films']}",
                flush=True,
            )
    return stats


def main() -> None:
    from app.db import Base, SessionLocal, engine

    parser = argparse.ArgumentParser(description="Exactly reconcile CMU records to Wikidata canonical films.")
    parser.add_argument("--page-size", type=int, default=100, help="Records per polite Wikidata source page")
    parser.add_argument("--limit", type=int, help="Optional test limit; omit for the full unresolved CMU corpus")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        stats = reconcile_cmu_records(db, page_size=args.page_size, limit=args.limit)
        print(f"Completed CMU reconciliation: {stats}")


if __name__ == "__main__":
    main()
