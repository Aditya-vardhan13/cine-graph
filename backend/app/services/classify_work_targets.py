"""Classify unresolved Wikidata work targets before exposing relationship cards."""
from __future__ import annotations

import argparse
from collections.abc import Callable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Assertion, CanonicalEntity, Film
from app.services.backfill_evidence_core import backfill
from app.services.wikidata import (
    _ingest_locked,
    fetch_rows_for_film_ids,
    item_id,
    sparql_query_runner,
)

TYPE_QIDS = {
    "film": "Q11424",
    "series": "Q5398426",
    "episode": "Q21191270",
    "book": "Q571",
    "play": "Q25379",
    "comic": "Q1004",
    "game": "Q7889",
}
TYPE_PRIORITY = {kind: index for index, kind in enumerate(TYPE_QIDS)}


def classify_targets(
    qids: list[str],
    runner: Callable[[str], list[dict]] | None = None,
) -> dict[str, tuple[str, str]]:
    """Return the best supported broad type and English label for each QID."""
    if not qids:
        return {}
    query = runner or sparql_query_runner()
    results: dict[str, tuple[str, str]] = {}
    for start in range(0, len(qids), 100):
        values = " ".join(f"wd:{qid}" for qid in qids[start:start + 100])
        type_values = " ".join(f"(wd:{qid} \"{kind}\")" for kind, qid in TYPE_QIDS.items())
        rows = query(f"""
          SELECT ?target ?targetLabel ?kind WHERE {{
            VALUES ?target {{ {values} }}
            VALUES (?class ?kind) {{ {type_values} }}
            ?target wdt:P31/wdt:P279* ?class.
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
          }}
        """)
        for row in rows:
            qid = item_id(row.get("target", {}).get("value"))
            kind = row.get("kind", {}).get("value")
            label = row.get("targetLabel", {}).get("value")
            if not qid or kind not in TYPE_PRIORITY or not label:
                continue
            existing = results.get(qid)
            if existing is None or TYPE_PRIORITY[kind] < TYPE_PRIORITY[existing[0]]:
                results[qid] = (kind, label)
    return results


def apply_classifications(
    db: Session,
    classifications: dict[str, tuple[str, str]],
    fetcher: Callable[[list[str]], list[dict]] | None = None,
) -> dict[str, int]:
    """Apply typed targets; import only classified film targets into the film projection."""
    stats = {"classified": 0, "films_imported": 0, "remaining_unknown": 0}
    if not classifications:
        stats["remaining_unknown"] = db.scalar(select(func.count()).select_from(CanonicalEntity).where(CanonicalEntity.entity_kind == "unknown_work")) or 0
        return stats
    entities = {
        entity.wikidata_id: entity
        for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.in_(classifications)))
    }
    for qid, (kind, label) in classifications.items():
        entity = entities.get(qid)
        if not entity:
            continue
        entity.entity_kind = kind
        entity.canonical_label = label
        db.execute(update(Assertion).where(
            Assertion.object_entity_id == entity.id,
            Assertion.review_status == "review_required",
        ).values(object_entity_kind=kind, review_status="resolved"))
        stats["classified"] += 1
    db.commit()

    # A retry must finish targets already classified in an earlier run whose
    # projection failed later in the pipeline.
    film_qids = list(db.scalars(select(CanonicalEntity.wikidata_id).join(
        Assertion, Assertion.object_entity_id == CanonicalEntity.id
    ).outerjoin(Film, Film.entity_id == CanonicalEntity.id).where(
        CanonicalEntity.entity_kind == "film",
        CanonicalEntity.wikidata_id.is_not(None),
        Film.id.is_(None),
    ).distinct()))
    if film_qids:
        rows = fetcher(film_qids) if fetcher else fetch_rows_for_film_ids(film_qids)
        batch = _ingest_locked(db, limit=len(film_qids), offset=0, rows=rows, external_reference="https://query.wikidata.org/#typed-work-target")
        stats["films_imported"] = batch.records_published
        backfill(db)
    stats["remaining_unknown"] = db.scalar(select(func.count()).select_from(CanonicalEntity).where(CanonicalEntity.entity_kind == "unknown_work")) or 0
    return stats


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Classify external work targets before publishing lineage.")
    parser.add_argument("--limit", type=int, help="Optional safety limit for a bounded classification run")
    args = parser.parse_args()
    run_migrations()
    with SessionLocal() as db:
        qids = list(db.scalars(select(CanonicalEntity.wikidata_id).where(
            CanonicalEntity.entity_kind == "unknown_work",
            CanonicalEntity.wikidata_id.is_not(None),
        ).limit(args.limit)))
        print(f"Typed target classification complete: {apply_classifications(db, classify_targets(qids))}")


if __name__ == "__main__":
    main()
