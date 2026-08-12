"""Backfill the additive evidence core from the legacy catalogue without rewriting it."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assertion,
    CanonicalEntity,
    CorpusRecord,
    DataSource,
    EntityAlias,
    ExternalWorkRelationship,
    Film,
    FilmAlias,
    FilmCredit,
    FilmReleaseEvent,
    FilmRelationship,
    Person,
    PersonAlias,
    SourceRecord,
)


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def payload_hash(value: Any) -> str:
    encoded = json.dumps(value, default=str, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _source_record(
    db: Session,
    records: dict[tuple[UUID, str], SourceRecord],
    source_id: UUID,
    external_id: str,
    source_reference: str,
    *,
    source_revision: str | None = None,
    rights_scope: str = "open",
    hash_value: str | None = None,
) -> SourceRecord:
    key = (source_id, external_id)
    if record := records.get(key):
        return record
    record = SourceRecord(
        source_id=source_id,
        external_id=external_id,
        source_revision=source_revision,
        payload_hash=hash_value,
        rights_scope=rights_scope,
        source_reference=source_reference,
    )
    db.add(record)
    records[key] = record
    return record


def _assertion(
    db: Session,
    seen: set[tuple[str, ...]],
    *,
    subject_id: UUID,
    predicate: str,
    object_id: UUID | None = None,
    object_kind: str | None = None,
    value_json: dict[str, Any] | None = None,
    source_id: UUID | None,
    source_record_id: UUID | None,
    source_reference: str,
    source_property: str | None = None,
    source_revision: str | None = None,
    review_status: str = "resolved",
) -> bool:
    value_key = json.dumps(value_json, sort_keys=True, default=str) if value_json is not None else ""
    key = (str(subject_id), predicate, str(object_id or ""), value_key, source_reference)
    if key in seen:
        return False
    seen.add(key)
    db.add(Assertion(
        subject_entity_id=subject_id,
        predicate=predicate,
        source_property=source_property,
        object_entity_id=object_id,
        object_entity_kind=object_kind,
        value_json=value_json,
        assertion_kind="source_fact",
        source_id=source_id,
        source_record_id=source_record_id,
        source_reference=source_reference,
        source_revision=source_revision,
        review_status=review_status,
    ))
    return True


def backfill(db: Session) -> dict[str, int]:
    """Populate only missing core records; safe to repeat after an interruption."""
    stats = {"entities": 0, "aliases": 0, "source_records": 0, "assertions": 0}
    sources = {source.id: source for source in db.scalars(select(DataSource))}
    entities_by_qid = {entity.wikidata_id: entity for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.is_not(None)))}
    records = {(record.source_id, record.external_id): record for record in db.scalars(select(SourceRecord))}
    alias_keys = {
        (alias.entity_id, alias.value, alias.language_code, alias.alias_kind)
        for alias in db.scalars(select(EntityAlias))
    }
    assertion_keys = {
        (str(item.subject_entity_id), item.predicate, str(item.object_entity_id or ""), json.dumps(item.value_json, sort_keys=True, default=str) if item.value_json is not None else "", item.source_reference or "")
        for item in db.scalars(select(Assertion))
    }

    def entity(kind: str, label: str, qid: str | None) -> CanonicalEntity:
        if qid and (existing := entities_by_qid.get(qid)):
            if existing.entity_kind == "unknown_work" and kind != "unknown_work":
                existing.entity_kind = kind
            if existing.canonical_label == qid and label != qid:
                existing.canonical_label = label
            return existing
        item = CanonicalEntity(entity_kind=kind, canonical_label=label, wikidata_id=qid)
        db.add(item)
        if qid:
            entities_by_qid[qid] = item
        stats["entities"] += 1
        return item

    films = list(db.scalars(select(Film)))
    people = list(db.scalars(select(Person)))
    for film in films:
        if not film.entity_id:
            item = entity("film", film.canonical_title, film.wikidata_id)
            film.entity = item
    for person in people:
        if not person.entity_id:
            item = entity("person", person.canonical_name, person.wikidata_id)
            person.entity = item
    db.commit()

    films_by_id = {film.id: film for film in films}
    people_by_id = {person.id: person for person in people}
    for alias in db.scalars(select(FilmAlias)):
        film = films_by_id[alias.film_id]
        key = (film.entity_id, alias.value, alias.language_code, "title")
        if key not in alias_keys:
            db.add(EntityAlias(
                entity_id=film.entity_id, value=alias.value, normalized_value=alias.normalized_value,
                language_code=alias.language_code, alias_kind="title",
            ))
            alias_keys.add(key)
            stats["aliases"] += 1
    for alias in db.scalars(select(PersonAlias)):
        person = people_by_id[alias.person_id]
        key = (person.entity_id, alias.value, alias.language_code, "credited_name")
        if key not in alias_keys:
            db.add(EntityAlias(
                entity_id=person.entity_id, value=alias.value, normalized_value=alias.normalized_value,
                language_code=alias.language_code, alias_kind="credited_name",
            ))
            alias_keys.add(key)
            stats["aliases"] += 1
    db.commit()

    # Each CMU row becomes an immutable source-record descriptor. Its licensed
    # plot remains in NarrativeDocument and is never copied into assertions.
    for row in db.scalars(select(CorpusRecord)):
        source = sources[row.source_id]
        before = len(records)
        _source_record(
            db, records, row.source_id, row.external_id, source.url,
            source_revision=row.source_revision, rights_scope="attributed_reference",
            hash_value=payload_hash({"title": row.title, "release_date": row.release_date, "raw_metadata": row.raw_metadata}),
        )
        stats["source_records"] += len(records) - before

    def film_source_record(film: Film, source_id: UUID, reference: str) -> SourceRecord:
        before = len(records)
        record = _source_record(
            db, records, source_id, film.wikidata_id or str(film.id), reference,
            rights_scope="open",
        )
        stats["source_records"] += len(records) - before
        if record.id is None:
            db.flush()
        return record

    for event in db.scalars(select(FilmReleaseEvent)):
        film = films_by_id[event.film_id]
        record = film_source_record(film, event.source_id, event.source_reference)
        if _assertion(
            db, assertion_keys, subject_id=film.entity_id, predicate="release_event",
            value_json={"date": event.release_date.isoformat(), "locations": event.location_ids, "event_type": event.event_type},
            source_id=event.source_id, source_record_id=record.id, source_reference=event.source_reference,
        ):
            stats["assertions"] += 1

    for credit in db.scalars(select(FilmCredit)):
        film, person = films_by_id[credit.film_id], people_by_id[credit.person_id]
        record = film_source_record(film, credit.source_id, credit.source_reference)
        if _assertion(
            db, assertion_keys, subject_id=film.entity_id, predicate=credit.role,
            object_id=person.entity_id, object_kind="person", source_id=credit.source_id,
            source_record_id=record.id, source_reference=credit.source_reference,
        ):
            stats["assertions"] += 1

    for relation in db.scalars(select(FilmRelationship)):
        first, second = films_by_id[relation.from_film_id], films_by_id[relation.to_film_id]
        record = film_source_record(first, relation.source_id, relation.source_reference)
        if _assertion(
            db, assertion_keys, subject_id=first.entity_id, predicate=relation.relationship_type,
            object_id=second.entity_id, object_kind="film", source_id=relation.source_id,
            source_record_id=record.id, source_reference=relation.source_reference,
        ):
            stats["assertions"] += 1

    for relation in db.scalars(select(ExternalWorkRelationship)):
        film = films_by_id[relation.from_film_id]
        target = entity("unknown_work", relation.to_wikidata_id, relation.to_wikidata_id)
        db.flush()
        record = film_source_record(film, relation.source_id, relation.source_reference)
        if _assertion(
            db, assertion_keys, subject_id=film.entity_id, predicate=relation.relationship_type,
            object_id=target.id, object_kind=target.entity_kind, source_id=relation.source_id,
            source_record_id=record.id, source_reference=relation.source_reference,
            review_status="review_required" if target.entity_kind == "unknown_work" else "resolved",
        ):
            stats["assertions"] += 1

    db.commit()
    return stats


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Idempotently backfill the stable evidence core from the legacy catalogue.")
    parser.parse_args()
    run_migrations()
    with SessionLocal() as db:
        print(f"Evidence-core backfill complete: {backfill(db)}")


if __name__ == "__main__":
    main()
