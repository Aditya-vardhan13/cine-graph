"""A polite, rerunnable Wikidata metadata ingestion adapter.

Only CC0 structured metadata is requested. No Wikipedia text, posters, plots,
subtitles, or screenplay material is fetched or stored.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import re
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    DataSource,
    Film,
    FilmAlias,
    FilmCredit,
    FilmReleaseEvent,
    FilmGenre,
    FilmProvenance,
    ExternalWorkRelationship,
    Genre,
    IngestionBatch,
    LanguageEdition,
    Person,
    PersonAlias,
    PersonProvenance,
)

ENDPOINT = "https://query.wikidata.org/sparql"
SOURCE_URL = "https://www.wikidata.org/"
SOURCE_REFERENCE = "https://query.wikidata.org/"
ACCESS_POLICY_URL = "https://www.wikidata.org/wiki/Wikidata:Data_access"
MIN_REQUEST_INTERVAL_SECONDS = 1.0
INGESTION_LOCK_PATH = "/tmp/cinegraph-wikidata-ingestion.lock"
WIKIDATA_ITEM = re.compile(r"/(Q\d+)$")


class WikidataIngestionError(RuntimeError):
    pass


@contextmanager
def exclusive_ingestion_lock() -> Any:
    """Prevent concurrent local imports from duplicating work or locking SQLite."""
    with open(INGESTION_LOCK_PATH, "w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WikidataIngestionError("A Wikidata ingestion is already running; wait for it to finish.") from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def item_id(value: str | None) -> str | None:
    if not value:
        return None
    match = WIKIDATA_ITEM.search(value)
    return match.group(1) if match else None


def clean_label(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _value(row: dict[str, Any], key: str) -> str | None:
    return row.get(key, {}).get("value")


def sparql_query_runner() -> Callable[[str], list[dict[str, Any]]]:
    """Create one polite, rate-limited Wikidata query session for a job."""
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": get_settings().wikidata_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }

    last_request_at = 0.0

    def run_query(query: str) -> list[dict[str, Any]]:
        nonlocal last_request_at
        for attempt in range(4):
            pause = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request_at)
            if pause > 0:
                time.sleep(pause)
            with httpx.Client(timeout=90, headers=headers) as client:
                response = client.post(ENDPOINT, data={"query": query, "format": "json"})
            last_request_at = time.monotonic()
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "60"))
                time.sleep(retry_after)
                continue
            if response.status_code in {403, 401}:
                raise WikidataIngestionError(
                    f"Wikidata denied the request (HTTP {response.status_code}); stopping rather than bypassing access controls."
                )
            if response.status_code in {502, 503, 504} and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()["results"]["bindings"]
        raise WikidataIngestionError("Wikidata remained unavailable after bounded, polite retries.")
    return run_query


def enrich_film_rows(
    film_rows: list[dict[str, Any]],
    run_query: Callable[[str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Keep independent relationships separate to avoid Cartesian explosion."""
    by_film = {item_id(_value(row, "film")): row for row in film_rows if item_id(_value(row, "film"))}
    film_ids = list(by_film)
    enriched: list[dict[str, Any]] = list(by_film.values())
    for start in range(0, len(film_ids), 100):
        values = " ".join(f"wd:{qid}" for qid in film_ids[start:start + 100])
        genre_rows = run_query(f"""
          SELECT ?film ?genre ?genreLabel WHERE {{
            VALUES ?film {{ {values} }}
            ?film wdt:P136 ?genre.
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
          }}
        """)
        country_rows = run_query(f"""
          SELECT ?film ?country WHERE {{
            VALUES ?film {{ {values} }}
            ?film wdt:P495 ?country.
          }}
        """)
        release_rows = run_query(f"""
          SELECT ?film ?releaseDate ?releasePlace WHERE {{
            VALUES ?film {{ {values} }}
            ?film p:P577 ?releaseStatement.
            ?releaseStatement ps:P577 ?releaseDate.
            OPTIONAL {{ ?releaseStatement pq:P291 ?releasePlace. }}
          }}
        """)
        relationship_rows = run_query(f"""
          SELECT ?film ?relatedWork ?relationship WHERE {{
            VALUES ?film {{ {values} }}
            {{ ?film wdt:P155 ?relatedWork. BIND("follows" AS ?relationship) }}
            UNION {{ ?film wdt:P156 ?relatedWork. BIND("followed_by" AS ?relationship) }}
            UNION {{ ?film wdt:P144 ?relatedWork. BIND("based_on" AS ?relationship) }}
            UNION {{ ?film wdt:P179 ?relatedWork. BIND("part_of_series" AS ?relationship) }}
          }}
        """)
        credit_rows = run_query(f"""
          SELECT ?film ?person ?personLabel ?role WHERE {{
            VALUES ?film {{ {values} }}
            {{ ?film wdt:P57 ?person. BIND("director" AS ?role) }}
            UNION {{ ?film wdt:P58 ?person. BIND("writer" AS ?role) }}
            UNION {{ ?film wdt:P161 ?person. BIND("cast" AS ?role) }}
            UNION {{ ?film wdt:P162 ?person. BIND("producer" AS ?role) }}
            UNION {{ ?film wdt:P86 ?person. BIND("composer" AS ?role) }}
            UNION {{ ?film wdt:P344 ?person. BIND("cinematographer" AS ?role) }}
            UNION {{ ?film wdt:P1040 ?person. BIND("editor" AS ?role) }}
            UNION {{ ?film wdt:P2554 ?person. BIND("production_designer" AS ?role) }}
            UNION {{ ?film wdt:P2515 ?person. BIND("costume_designer" AS ?role) }}
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
          }}
        """)
        for row in [*genre_rows, *country_rows, *credit_rows, *release_rows, *relationship_rows]:
            header = by_film.get(item_id(_value(row, "film")))
            if header:
                enriched.append({**header, **row})
    return enriched


def fetch_rows(limit: int, offset: int = 0) -> list[dict[str, Any]]:
    # Keep independent relationships in separate queries. A single query would
    # multiply cast × genres × countries and becomes impractical at 1,000 films.
    run_query = sparql_query_runner()

    film_rows = run_query(f"""
      SELECT ?film ?filmLabel (SAMPLE(?runtimeValue) AS ?runtime) WHERE {{
        {{ SELECT ?film WHERE {{ ?film wdt:P31 wd:Q11424; wdt:P364 wd:Q1860. }} LIMIT {limit} OFFSET {offset} }}
        OPTIONAL {{ ?film wdt:P2047 ?runtimeValue. }}
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }} GROUP BY ?film ?filmLabel
    """)
    return enrich_film_rows(film_rows, run_query)


def fetch_wikidata_ids_for_freebase(
    freebase_ids: list[str],
    run_query: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, set[str]]:
    """Resolve CMU's legacy Freebase IDs through Wikidata's direct P646 property."""
    if not freebase_ids:
        return {}
    if any(not re.fullmatch(r"/m/[A-Za-z0-9_-]+", freebase_id) for freebase_id in freebase_ids):
        raise WikidataIngestionError("Unexpected Freebase identifier; refusing to interpolate it into SPARQL")
    runner = run_query or sparql_query_runner()
    values = " ".join(json.dumps(freebase_id) for freebase_id in freebase_ids)
    mappings: dict[str, set[str]] = defaultdict(set)
    for row in runner(f"""
      SELECT ?film ?freebaseId WHERE {{
        VALUES ?freebaseId {{ {values} }}
        ?film wdt:P646 ?freebaseId.
      }}
    """):
        freebase_id, qid = _value(row, "freebaseId"), item_id(_value(row, "film"))
        if freebase_id and qid:
            mappings[freebase_id].add(qid)
    return mappings


def fetch_rows_for_film_ids(
    film_ids: list[str],
    run_query: Callable[[str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Fetch canonical facts for an already selected, identifier-backed set of films."""
    if not film_ids:
        return []
    if any(not re.fullmatch(r"Q\d+", film_id) for film_id in film_ids):
        raise WikidataIngestionError("Unexpected Wikidata identifier; refusing to interpolate it into SPARQL")
    runner = run_query or sparql_query_runner()
    values = " ".join(f"wd:{film_id}" for film_id in film_ids)
    headers = runner(f"""
      SELECT ?film ?filmLabel (SAMPLE(?runtimeValue) AS ?runtime) WHERE {{
        VALUES ?film {{ {values} }}
        OPTIONAL {{ ?film wdt:P2047 ?runtimeValue. }}
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }} GROUP BY ?film ?filmLabel
    """)
    return enrich_film_rows(headers, runner)


def ensure_language_editions(db: Session) -> None:
    editions = [
        ("en", "English", "English", "Latin", True, "live", "none"),
        ("te", "Telugu", "తెలుగు", "Telugu", False, "planned", "ISO 15919"),
        ("ta", "Tamil", "தமிழ்", "Tamil", False, "planned", "ISO 15919"),
        ("hi", "Hindi", "हिन्दी", "Devanagari", False, "planned", "ISO 15919"),
    ]
    for code, display, native, script, enabled, status, strategy in editions:
        if not db.get(LanguageEdition, code):
            db.add(LanguageEdition(
                code=code, display_name=display, native_name=native, script=script,
                enabled=enabled, status=status, transliteration_strategy=strategy,
            ))


def source_for_wikidata(db: Session) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == "Wikidata"))
    if source:
        return source
    source = DataSource(
        name="Wikidata",
        url=SOURCE_URL,
        source_type="structured_metadata",
        license="CC0 1.0",
        rights_status="open",
        notes=(
            "Phase A uses only Wikidata CC0 structured data through its documented query API. "
            f"API etiquette: {ACCESS_POLICY_URL}. No HTML pages are crawled; robots.txt applies to future HTML adapters."
        ),
    )
    db.add(source)
    db.flush()
    return source


def upsert_person(db: Session, wikidata_id: str, name: str, source: DataSource, batch: IngestionBatch) -> Person:
    person = db.scalar(select(Person).where(Person.wikidata_id == wikidata_id))
    if not person:
        person = Person(canonical_name=name, wikidata_id=wikidata_id)
        db.add(person)
        db.flush()
        db.add(PersonAlias(person_id=person.id, value=name, normalized_value=normalize(name), language_code="en"))
        db.add(PersonProvenance(person_id=person.id, source_id=source.id, batch_id=batch.id, field_name="canonical_name", source_reference=f"https://www.wikidata.org/wiki/{wikidata_id}"))
    return person


def upsert_genre(db: Session, wikidata_id: str, label: str) -> Genre:
    genre = db.scalar(select(Genre).where(Genre.wikidata_id == wikidata_id))
    if not genre:
        # The legacy projection keeps labels unique. Wikidata can legitimately
        # expose distinct genre items with the same English label, so reuse the
        # existing label projection instead of failing the whole import.
        genre = db.scalar(select(Genre).where(Genre.label == label))
        if genre:
            if genre.wikidata_id is None:
                genre.wikidata_id = wikidata_id
        else:
            genre = Genre(label=label, wikidata_id=wikidata_id)
            db.add(genre)
            db.flush()
    return genre


def ingest(
    db: Session,
    limit: int = 1000,
    offset: int = 0,
    rows: list[dict[str, Any]] | None = None,
    external_reference: str | None = None,
) -> IngestionBatch:
    with exclusive_ingestion_lock():
        return _ingest_locked(db, limit, offset, rows, external_reference)


def _ingest_locked(
    db: Session,
    limit: int,
    offset: int,
    rows: list[dict[str, Any]] | None,
    external_reference: str | None = None,
) -> IngestionBatch:
    ensure_language_editions(db)
    source = source_for_wikidata(db)
    batch = IngestionBatch(
        source_id=source.id,
        external_reference=external_reference or f"{ENDPOINT}?offset={offset}&limit={limit}",
        status="running",
    )
    db.add(batch)
    db.flush()
    rows = fetch_rows(limit, offset) if rows is None else rows

    films: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"genres": {}, "credits": {}, "countries": set(), "release_events": set(), "relationships": set()}
    )
    for row in rows:
        film_qid = item_id(_value(row, "film"))
        title = clean_label(_value(row, "filmLabel"))
        if not film_qid or not title:
            continue
        record = films[film_qid]
        record.update({"title": title, "runtime": _value(row, "runtime")})
        release_date = parse_date(_value(row, "releaseDate"))
        if release_date:
            record["release_events"].add((release_date, item_id(_value(row, "releasePlace"))))
        country = item_id(_value(row, "country"))
        if country:
            record["countries"].add(country)
        genre_qid, genre_label = item_id(_value(row, "genre")), clean_label(_value(row, "genreLabel"))
        if genre_qid and genre_label:
            record["genres"][genre_qid] = genre_label
        person_qid, person_label, role = item_id(_value(row, "person")), clean_label(_value(row, "personLabel")), _value(row, "role")
        if person_qid and person_label and role:
            record["credits"][(person_qid, role)] = person_label
        related_work, relationship_type = item_id(_value(row, "relatedWork")), _value(row, "relationship")
        if related_work and relationship_type:
            record["relationships"].add((related_work, relationship_type))

    for film_qid, record in films.items():
        film = db.scalar(select(Film).where(Film.wikidata_id == film_qid))
        runtime = int(float(record["runtime"])) if record["runtime"] else None
        selected_release_date = min((release_date for release_date, _ in record["release_events"]), default=None)
        if not film:
            film = Film(
                canonical_title=record["title"], wikidata_id=film_qid, release_date=selected_release_date,
                runtime_minutes=runtime, original_language_code="en", country_codes=sorted(record["countries"]),
            )
            db.add(film)
            db.flush()
            db.add(FilmAlias(film_id=film.id, value=record["title"], normalized_value=normalize(record["title"]), language_code="en"))
            for field in ("canonical_title", "release_date", "runtime_minutes", "original_language_code", "country_codes"):
                db.add(FilmProvenance(film_id=film.id, source_id=source.id, batch_id=batch.id, field_name=field, source_reference=f"https://www.wikidata.org/wiki/{film_qid}"))
        else:
            # A source page can contain multiple release assertions. Always use
            # the documented display policy, never source-row arrival order.
            film.release_date = selected_release_date or film.release_date
            film.runtime_minutes = runtime or film.runtime_minutes
            film.country_codes = sorted(record["countries"]) or film.country_codes
        release_places_by_date: dict[date, set[str]] = defaultdict(set)
        for release_date, release_place in record["release_events"]:
            if release_place:
                release_places_by_date[release_date].add(release_place)
            else:
                release_places_by_date.setdefault(release_date, set())
        for release_date, release_places in release_places_by_date.items():
            exists = db.scalar(select(FilmReleaseEvent).where(
                FilmReleaseEvent.film_id == film.id,
                FilmReleaseEvent.release_date == release_date,
                FilmReleaseEvent.source_id == source.id,
                FilmReleaseEvent.source_reference == f"https://www.wikidata.org/wiki/{film_qid}",
            ))
            if not exists:
                db.add(FilmReleaseEvent(
                    film_id=film.id, release_date=release_date, location_ids=sorted(release_places),
                    source_id=source.id, batch_id=batch.id, source_reference=f"https://www.wikidata.org/wiki/{film_qid}",
                ))
        for related_work, relationship_type in record["relationships"]:
            exists = db.scalar(select(ExternalWorkRelationship).where(
                ExternalWorkRelationship.from_film_id == film.id,
                ExternalWorkRelationship.to_wikidata_id == related_work,
                ExternalWorkRelationship.relationship_type == relationship_type,
                ExternalWorkRelationship.source_id == source.id,
            ))
            if not exists:
                db.add(ExternalWorkRelationship(
                    from_film_id=film.id, to_wikidata_id=related_work, relationship_type=relationship_type,
                    source_id=source.id, source_reference=f"https://www.wikidata.org/wiki/{film_qid}",
                ))
        for genre_qid, genre_label in record["genres"].items():
            genre = upsert_genre(db, genre_qid, genre_label)
            exists = db.scalar(select(FilmGenre).where(FilmGenre.film_id == film.id, FilmGenre.genre_id == genre.id))
            if not exists:
                db.add(FilmGenre(film_id=film.id, genre_id=genre.id, source_id=source.id, source_reference=f"https://www.wikidata.org/wiki/{film_qid}"))
        for (person_qid, role), person_name in record["credits"].items():
            person = upsert_person(db, person_qid, person_name, source, batch)
            exists = db.scalar(select(FilmCredit).where(FilmCredit.film_id == film.id, FilmCredit.person_id == person.id, FilmCredit.role == role))
            if not exists:
                db.add(FilmCredit(film_id=film.id, person_id=person.id, role=role, source_id=source.id, source_reference=f"https://www.wikidata.org/wiki/{film_qid}"))
    # These batch counters describe source *entities* (films), not the many
    # relationship rows used to enrich each entity.
    batch.records_received = len(films)
    batch.records_published = len(films)
    batch.records_rejected = 0
    batch.status = "complete"
    db.commit()
    return batch


def main() -> None:
    from app.db import Base, SessionLocal, engine
    parser = argparse.ArgumentParser(description="Ingest CC0 English-language film metadata from Wikidata.")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1 or args.offset < 0 or args.page_size < 1:
        parser.error("--limit and --page-size must be positive; --offset cannot be negative")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        total_published = 0
        for page_offset in range(args.offset, args.offset + args.limit, args.page_size):
            page_limit = min(args.page_size, args.offset + args.limit - page_offset)
            batch = ingest(db, limit=page_limit, offset=page_offset)
            total_published += batch.records_published
            print(f"Completed batch {batch.id}: {batch.records_published} films at offset {page_offset}")
        print(f"Completed {total_published} films across resumable source batches")


if __name__ == "__main__":
    main()
