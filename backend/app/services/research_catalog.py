"""Read model for films that are ready for narrative research.

The narrative corpus is keyed by ``CanonicalEntity``.  A legacy ``Film``
profile is optional and must not determine whether a retained research film is
searchable.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Assertion, CanonicalEntity, Genre, ReferenceCollectionMembership
from app.services.research_metadata import METADATA_PREDICATES, MetadataAssertion, display_metadata


DEFAULT_RESEARCH_COLLECTION = "english-1000-retained-narrative-v1"
_FILM_DISAMBIGUATION = re.compile(r"\s+\(\d{4} film\)$", re.IGNORECASE)


def display_film_title(canonical_label: str) -> str:
    """Remove only MediaWiki's year-film disambiguator from display copy."""
    return _FILM_DISAMBIGUATION.sub("", canonical_label).strip()


@dataclass(frozen=True)
class ResearchFilm:
    entity_id: UUID
    film_id: UUID | None
    title: str
    release_date: str | None
    runtime_minutes: int | None
    genres: tuple[str, ...]
    language_code: str
    release_year: int | None
    release_basis: str | None
    genre_ids: tuple[str, ...]
    original_language_ids: tuple[str, ...]
    metadata_issues: tuple[str, ...]
    metadata_evidence: dict[str, list[dict[str, str | None]]]


def research_films_from_entities(db: Session, entities: list[CanonicalEntity]) -> tuple[ResearchFilm, ...]:
    if not entities:
        return ()
    assertions = db.scalars(select(Assertion).where(
        Assertion.subject_entity_id.in_([e.id for e in entities]),
        Assertion.predicate.in_(METADATA_PREDICATES),
        Assertion.assertion_kind == "source_fact",
        Assertion.review_status.in_(("resolved", "published")),
    )).all()
    genre_ids = {a.value_json.get("wikidata_id") for a in assertions
                 if a.predicate == "genre" and a.value_json}
    labels = dict(db.execute(select(Genre.wikidata_id, Genre.label).where(
        Genre.wikidata_id.in_(genre_ids)
    )).all()) if genre_ids else {}
    by_entity: dict[UUID, list[MetadataAssertion]] = {e.id: [] for e in entities}
    for assertion in assertions:
        by_entity[assertion.subject_entity_id].append(MetadataAssertion(
            str(assertion.id), assertion.predicate, assertion.value_json or {},
            assertion.qualifiers or {}, assertion.review_status, assertion.rank,
            assertion.source_reference or "", assertion.source_revision,
        ))
    return tuple(ResearchFilm(
        entity_id=entity.id, film_id=entity.film_profile.id if entity.film_profile else None,
        title=display_film_title(entity.canonical_label),
        **display_metadata(by_entity[entity.id], genre_labels=labels),
    ) for entity in entities)


def _research_entity_query(collection_code: str):
    return (
        select(CanonicalEntity)
        .join(
            ReferenceCollectionMembership,
            ReferenceCollectionMembership.entity_id == CanonicalEntity.id,
        )
        .options(selectinload(CanonicalEntity.film_profile))
        .where(
            ReferenceCollectionMembership.collection_code == collection_code,
            CanonicalEntity.entity_kind == "film",
            CanonicalEntity.lifecycle_status == "active",
        )
    )


def get_research_film(
    db: Session,
    entity_id: UUID,
    *,
    collection_code: str = DEFAULT_RESEARCH_COLLECTION,
) -> ResearchFilm | None:
    entity = db.scalar(_research_entity_query(collection_code).where(CanonicalEntity.id == entity_id))
    return research_films_from_entities(db, [entity])[0] if entity else None


def search_research_films(
    db: Session,
    *,
    query_text: str,
    limit: int = 8,
    collection_code: str = DEFAULT_RESEARCH_COLLECTION,
) -> tuple[ResearchFilm, ...]:
    normalized = query_text.strip()
    if not normalized:
        return ()
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    lowered_query = normalized.casefold()
    label = CanonicalEntity.canonical_label
    display_label = func.regexp_replace(label, r" \([0-9]{4} film\)$", "", "i")
    relevance = case(
        (func.lower(display_label) == lowered_query, 0),
        (func.lower(display_label).like(f"{lowered_query}%"), 1),
        else_=2,
    )
    entities = db.scalars(
        _research_entity_query(collection_code)
        .where(label.ilike(f"%{normalized}%"))
        .order_by(relevance, func.length(display_label), label)
        .limit(limit)
    ).unique().all()
    return research_films_from_entities(db, list(entities))
