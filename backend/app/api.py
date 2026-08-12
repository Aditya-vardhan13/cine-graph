from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import (
    DataSource, Film, FilmCredit, FilmGenre, FilmProvenance, Genre, IngestionBatch,
    LanguageEdition, Person, PersonProvenance,
)
from app.schemas import (
    CreditOut, FilmDetail, FilmListItem, GraphEdge, GraphNode, GraphOut, HealthOut,
    LanguageEditionOut, PersonDetail, ProvenanceOut, SimilarFilmOut, SimilarityFactor,
)

router = APIRouter(prefix="/api/v1")


def film_item(film: Film) -> FilmListItem:
    return FilmListItem(
        id=film.id, title=film.canonical_title, release_date=film.release_date,
        runtime_minutes=film.runtime_minutes, genres=sorted({link.genre.label for link in film.genres}),
        language_code=film.original_language_code,
    )


def provenance_for_film(db: Session, film: Film) -> list[ProvenanceOut]:
    rows = db.execute(
        select(FilmProvenance, DataSource).join(DataSource).where(FilmProvenance.film_id == film.id)
    ).all()
    return [ProvenanceOut(source_name=s.name, source_url=s.url, license=s.license, field_name=p.field_name, source_reference=p.source_reference) for p, s in rows]


@router.get("/health", response_model=HealthOut)
def catalog_health(db: Session = Depends(get_db)) -> HealthOut:
    latest = db.scalar(select(func.max(IngestionBatch.acquired_at)))
    editions = db.scalars(select(LanguageEdition).order_by(LanguageEdition.enabled.desc(), LanguageEdition.display_name)).all()
    return HealthOut(
        status="ready" if db.scalar(select(func.count()).select_from(Film)) else "empty",
        films=db.scalar(select(func.count()).select_from(Film)) or 0,
        people=db.scalar(select(func.count()).select_from(Person)) or 0,
        credits=db.scalar(select(func.count()).select_from(FilmCredit)) or 0,
        sources=db.scalar(select(func.count()).select_from(DataSource)) or 0,
        latest_ingestion_at=latest,
        language_editions=[LanguageEditionOut.model_validate(item, from_attributes=True) for item in editions],
    )


@router.get("/languages", response_model=list[LanguageEditionOut])
def languages(db: Session = Depends(get_db)) -> list[LanguageEditionOut]:
    editions = db.scalars(select(LanguageEdition).order_by(LanguageEdition.enabled.desc(), LanguageEdition.display_name)).all()
    return [LanguageEditionOut.model_validate(item, from_attributes=True) for item in editions]


@router.get("/films", response_model=list[FilmListItem])
def list_films(
    q: str | None = Query(default=None, min_length=1),
    genre: str | None = None,
    decade: int | None = Query(default=None, ge=1880, le=2100),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[FilmListItem]:
    query = select(Film).options(selectinload(Film.genres).selectinload(FilmGenre.genre)).where(Film.review_status == "published")
    if q:
        query = query.where(Film.canonical_title.ilike(f"%{q.strip()}%"))
    if genre:
        query = query.join(FilmGenre).join(Genre).where(Genre.label.ilike(genre.strip()))
    if decade:
        query = query.where(Film.release_date >= datetime(decade, 1, 1), Film.release_date < datetime(decade + 10, 1, 1))
    films = db.scalars(query.order_by(Film.release_date.desc(), Film.canonical_title).offset(offset).limit(limit)).unique().all()
    return [film_item(film) for film in films]


@router.get("/films/{film_id}", response_model=FilmDetail)
def get_film(film_id: UUID, db: Session = Depends(get_db)) -> FilmDetail:
    film = db.scalar(
        select(Film).options(
            selectinload(Film.aliases), selectinload(Film.genres).selectinload(FilmGenre.genre),
            selectinload(Film.credits).selectinload(FilmCredit.person),
        ).where(Film.id == film_id)
    )
    if not film:
        raise HTTPException(status_code=404, detail="Film not found")
    item = film_item(film)
    return FilmDetail(
        **item.model_dump(), wikidata_id=film.wikidata_id, countries=film.country_codes,
        aliases=[alias.value for alias in film.aliases],
        credits=[CreditOut(person_id=credit.person.id, name=credit.person.canonical_name, role=credit.role, character_name=credit.character_name) for credit in sorted(film.credits, key=lambda c: (c.role, c.person.canonical_name))],
        provenance=provenance_for_film(db, film),
    )


@router.get("/people/{person_id}", response_model=PersonDetail)
def get_person(person_id: UUID, db: Session = Depends(get_db)) -> PersonDetail:
    person = db.scalar(select(Person).options(selectinload(Person.aliases), selectinload(Person.credits).selectinload(FilmCredit.film).selectinload(Film.genres).selectinload(FilmGenre.genre)).where(Person.id == person_id))
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    provenance = db.execute(select(PersonProvenance, DataSource).join(DataSource).where(PersonProvenance.person_id == person.id)).all()
    unique_films = {credit.film.id: credit.film for credit in person.credits}.values()
    return PersonDetail(
        id=person.id, name=person.canonical_name, wikidata_id=person.wikidata_id,
        aliases=[alias.value for alias in person.aliases], films=[film_item(film) for film in sorted(unique_films, key=lambda f: f.release_date or datetime.min.date(), reverse=True)],
        provenance=[ProvenanceOut(source_name=s.name, source_url=s.url, license=s.license, field_name=p.field_name, source_reference=p.source_reference) for p, s in provenance],
    )


@router.get("/films/{film_id}/graph", response_model=GraphOut)
def film_graph(film_id: UUID, max_people: int = Query(default=16, ge=1, le=50), db: Session = Depends(get_db)) -> GraphOut:
    film = db.scalar(select(Film).options(selectinload(Film.credits).selectinload(FilmCredit.person)).where(Film.id == film_id))
    if not film:
        raise HTTPException(status_code=404, detail="Film not found")
    credits = sorted(film.credits, key=lambda c: (c.role != "director", c.role != "writer", c.person.canonical_name))
    shown = credits[:max_people]
    nodes = [GraphNode(id=f"film:{film.id}", label=film.canonical_title, type="film")]
    edges: list[GraphEdge] = []
    for credit in shown:
        nodes.append(GraphNode(id=f"person:{credit.person.id}", label=credit.person.canonical_name, type="person"))
        edges.append(GraphEdge(source=f"person:{credit.person.id}", target=f"film:{film.id}", label=credit.role, evidence=credit.source_reference))
    return GraphOut(center_id=f"film:{film.id}", nodes=nodes, edges=edges, truncated=len(credits) > len(shown))


@router.get("/films/{film_id}/similar", response_model=list[SimilarFilmOut])
def similar_films(film_id: UUID, limit: int = Query(default=8, ge=1, le=20), db: Session = Depends(get_db)) -> list[SimilarFilmOut]:
    target = db.scalar(select(Film).options(selectinload(Film.genres).selectinload(FilmGenre.genre), selectinload(Film.credits)).where(Film.id == film_id))
    if not target:
        raise HTTPException(status_code=404, detail="Film not found")
    candidates = db.scalars(select(Film).options(selectinload(Film.genres).selectinload(FilmGenre.genre), selectinload(Film.credits)).where(Film.id != film_id, Film.review_status == "published")).unique().all()
    target_genres = {link.genre.label for link in target.genres}
    target_people = {credit.person_id for credit in target.credits}
    target_year = target.release_date.year if target.release_date else None
    scored: list[SimilarFilmOut] = []
    for candidate in candidates:
        factors: list[SimilarityFactor] = []
        score = 0.0
        genres = {link.genre.label for link in candidate.genres}
        overlap = target_genres & genres
        if overlap:
            contribution = min(45.0, 15.0 * len(overlap))
            score += contribution
            factors.append(SimilarityFactor(label="Shared genres", weight=0.45, contribution=contribution, evidence=", ".join(sorted(overlap))))
        people = {credit.person_id for credit in candidate.credits}
        shared_people = target_people & people
        if shared_people:
            contribution = min(35.0, 12.0 * len(shared_people))
            score += contribution
            factors.append(SimilarityFactor(label="Shared credited people", weight=0.35, contribution=contribution, evidence=f"{len(shared_people)} shared credit(s)"))
        if target_year and candidate.release_date:
            distance = abs(target_year - candidate.release_date.year)
            if distance <= 10:
                contribution = round(20.0 * (1 - distance / 10), 1)
                score += contribution
                factors.append(SimilarityFactor(label="Release era", weight=0.20, contribution=contribution, evidence=f"{distance} year(s) apart"))
        if score > 0:
            item = film_item(candidate)
            scored.append(SimilarFilmOut(**item.model_dump(), score=round(min(score, 100.0), 1), factors=factors))
    return sorted(scored, key=lambda item: (-item.score, item.title))[:limit]
