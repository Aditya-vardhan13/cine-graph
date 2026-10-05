"""Join duplicate local IMDb film entities to verified Wikidata film identities.

Only an operator-selected manifest is considered. The old entity is retained
with lifecycle_status=merged; source facts and evidence IDs are not deleted.
Any unexpected foreign-key reference aborts the merge for manual review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal
from app.models import (
    Assertion, CanonicalEntity, DataSource, EntityResolution, Film,
    ReferenceCollectionMembership, SourceAssertion, SourceObject, SourceSnapshot,
)
from app.services.movie_data_gateway import MovieSeed, manifest_seeds
from app.services.source_assertion_policy import project_wikidata_statement


MOVABLE = {
    "entity_resolutions.entity_id", "assertions.subject_entity_id",
    "reference_collection_memberships.entity_id", "films.entity_id",
}


def _references(db: Session, entity_id: UUID) -> dict[str, int]:
    found = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if any(fk.target_fullname == "canonical_entities.id" for fk in column.foreign_keys):
                count = db.scalar(select(func.count()).select_from(table).where(
                    column == entity_id,
                )) or 0
                if count:
                    found[f"{table.name}.{column.name}"] = count
    return found


def imdb_film_for_identifier(db: Session, imdb_id: str) -> Film | None:
    return db.scalar(select(Film).join(
        EntityResolution, EntityResolution.entity_id == Film.entity_id,
    ).join(SourceObject, SourceObject.id == EntityResolution.source_object_id
    ).join(DataSource, DataSource.id == SourceObject.source_id).where(
        DataSource.name == "IMDb Non-Commercial Datasets",
        SourceObject.external_id == imdb_id,
        EntityResolution.status == "resolved",
    ))


def prepare_qid_subject(db: Session, seed: MovieSeed, *, apply: bool) -> dict:
    """Classify a Wikidata subject only when retained P31/P345 agree."""
    if not seed.wikidata_id or not seed.imdb_id:
        raise ValueError("Manifest line needs explicit IMDb and Wikidata IDs")
    source = db.scalar(select(DataSource).where(DataSource.name == "Wikidata"))
    item = db.scalar(select(SourceObject).where(
        SourceObject.source_id == source.id if source else False,
        SourceObject.external_id == seed.wikidata_id,
    ))
    latest = db.scalar(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id == item.id if item else False,
        SourceSnapshot.fetch_status == "success",
    ).order_by(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc()))
    if latest is None:
        raise ValueError("No retained Wikidata source snapshot")
    decisions = [project_wikidata_statement(raw.source_property, raw.raw_value)
                 for raw in db.scalars(select(SourceAssertion).where(
                     SourceAssertion.source_snapshot_id == latest.id,
                     SourceAssertion.source_property.in_(("P31", "P345")),
                 ))]
    is_film = any(decision.outcome == "project" and
                  decision.predicate == "instance_of" and
                  (decision.value_json or {}).get("wikidata_id") == "Q11424"
                  for decision in decisions)
    id_matches = any(decision.outcome == "project" and
                     decision.predicate == "imdb_identifier" and
                     (decision.value_json or {}).get("value") == seed.imdb_id
                     for decision in decisions)
    if not (is_film and id_matches):
        raise ValueError("Retained Wikidata P31/P345 do not prove this film identity")
    entity = db.scalar(select(CanonicalEntity).where(
        CanonicalEntity.wikidata_id == seed.wikidata_id,
    ))
    if entity and entity.entity_kind not in {"film", "unknown_work"}:
        raise ValueError("QID is already classified as a different entity kind")
    status = "already_film" if entity and entity.entity_kind == "film" else (
        "promote_unknown_work" if entity else "create_film_subject")
    if apply:
        if entity and entity.entity_kind == "unknown_work":
            entity.entity_kind = "film"
        elif entity is None:
            entity = CanonicalEntity(entity_kind="film", canonical_label=seed.title,
                                     wikidata_id=seed.wikidata_id)
            db.add(entity)
        db.flush()
    return {"title": seed.title, "imdb_id": seed.imdb_id,
            "wikidata_id": seed.wikidata_id, "status": status,
            "entity_id": str(entity.id) if entity else None}


def reconcile_one(db: Session, seed: MovieSeed, *, apply: bool) -> dict:
    if not seed.imdb_id or not seed.wikidata_id:
        raise ValueError("Manifest line needs explicit IMDb and Wikidata IDs")
    film = imdb_film_for_identifier(db, seed.imdb_id)
    target = db.scalar(select(CanonicalEntity).where(
        CanonicalEntity.wikidata_id == seed.wikidata_id,
    ))
    if film is None or target is None:
        raise ValueError("Both source identities must exist before reconciliation")
    if film.entity_id == target.id:
        return {"title": seed.title, "status": "already_unified"}
    old = db.get(CanonicalEntity, film.entity_id)
    if old.wikidata_id or old.entity_kind != "film" or target.entity_kind != "film":
        raise ValueError("Both entities must be correctly typed and old entity must have no QID")
    if db.scalar(select(Film.id).where(Film.entity_id == target.id)):
        raise ValueError("Target QID entity already has a film profile")
    wikidata = db.scalar(select(DataSource).where(DataSource.name == "Wikidata"))
    imdb = db.scalar(select(DataSource).where(DataSource.name == "IMDb Non-Commercial Datasets"))
    if not wikidata or not imdb:
        raise ValueError("Required source registrations are missing")
    target_facts = list(db.scalars(select(Assertion).where(
        Assertion.subject_entity_id == target.id,
        Assertion.source_id == wikidata.id,
        Assertion.review_status.in_(("resolved", "published")),
        Assertion.predicate.in_(("instance_of", "imdb_identifier")),
    )))
    film_type = any(row.predicate == "instance_of" and
                    (row.value_json or {}).get("wikidata_id") == "Q11424"
                    for row in target_facts)
    same_id = any(row.predicate == "imdb_identifier" and
                  (row.value_json or {}).get("value") == seed.imdb_id
                  for row in target_facts)
    old_id = any((row.value_json or {}).get("value") == seed.imdb_id for row in
                 db.scalars(select(Assertion).where(
                     Assertion.subject_entity_id == old.id,
                     Assertion.source_id == imdb.id,
                     Assertion.predicate == "imdb_identifier",
                     Assertion.review_status.in_(("resolved", "published")),
                 )))
    if not (film_type and same_id and old_id):
        raise ValueError("Reviewed source assertions do not prove the identity merge")
    references = _references(db, old.id)
    unexpected = set(references) - MOVABLE
    if unexpected:
        raise ValueError(f"Unexpected references need review: {sorted(unexpected)}")
    old_collections = set(db.scalars(select(ReferenceCollectionMembership.collection_code).where(
        ReferenceCollectionMembership.entity_id == old.id,
    )))
    target_collections = set(db.scalars(select(ReferenceCollectionMembership.collection_code).where(
        ReferenceCollectionMembership.entity_id == target.id,
    )))
    if old_collections & target_collections:
        raise ValueError("Both entities already belong to the same collection")
    report = {"title": seed.title, "imdb_id": seed.imdb_id,
              "wikidata_id": seed.wikidata_id, "old_entity_id": str(old.id),
              "target_entity_id": str(target.id), "moved_references": references,
              "status": "ready" if not apply else "merged"}
    if not apply:
        return report
    for table_name, column_name in (
        ("entity_resolutions", "entity_id"),
        ("assertions", "subject_entity_id"),
        ("reference_collection_memberships", "entity_id"),
    ):
        table = Base.metadata.tables[table_name]
        column = table.c[column_name]
        db.execute(update(table).where(column == old.id).values({column_name: target.id}))
    film.entity_id = target.id
    film.wikidata_id = seed.wikidata_id
    old.lifecycle_status = "merged"
    db.flush()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile explicit IMDb/Wikidata film identities")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Perform source-proven merges")
    parser.add_argument("--prepare-qids", action="store_true",
                        help="Classify missing QID subjects from retained P31/P345 before projection")
    args = parser.parse_args()
    results = []
    with SessionLocal() as db:
        for seed in manifest_seeds(args.manifest):
            try:
                result = (prepare_qid_subject(db, seed, apply=args.apply)
                          if args.prepare_qids else reconcile_one(db, seed, apply=args.apply))
                if args.apply:
                    db.commit()
                results.append(result)
            except Exception as exc:
                db.rollback()
                results.append({"title": seed.title, "status": "review_required",
                                "reason": f"{type(exc).__name__}: {exc}"})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(json.dumps({"ready_or_merged": sum(row["status"] in {
                          "ready", "merged", "already_unified", "already_film",
                          "promote_unknown_work", "create_film_subject",
                      }
                                               for row in results),
                      "review_required": sum(row["status"] == "review_required" for row in results),
                      "report": str(args.report)}))


if __name__ == "__main__":
    main()
