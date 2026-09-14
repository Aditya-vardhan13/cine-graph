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

from app.models import CanonicalEntity, Film, FilmGenre, ReferenceCollectionMembership


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


def research_film_from_entity(entity: CanonicalEntity) -> ResearchFilm:
    profile = entity.film_profile
    return ResearchFilm(
        entity_id=entity.id,
        film_id=profile.id if profile else None,
        title=profile.canonical_title if profile else display_film_title(entity.canonical_label),
        release_date=profile.release_date.isoformat() if profile and profile.release_date else None,
        runtime_minutes=profile.runtime_minutes if profile else None,
        genres=tuple(sorted(link.genre.label for link in profile.genres)) if profile else (),
        language_code=profile.original_language_code if profile else "en",
    )


def _research_entity_query(collection_code: str):
    return (
        select(CanonicalEntity)
        .join(
            ReferenceCollectionMembership,
            ReferenceCollectionMembership.entity_id == CanonicalEntity.id,
        )
        .options(
            selectinload(CanonicalEntity.film_profile)
            .selectinload(Film.genres)
            .selectinload(FilmGenre.genre)
        )
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
    return research_film_from_entity(entity) if entity else None


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
    return tuple(research_film_from_entity(entity) for entity in entities)
