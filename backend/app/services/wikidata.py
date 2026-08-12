"""A polite, rerunnable Wikidata metadata ingestion adapter.

Only CC0 structured metadata is requested. No Wikipedia text, posters, plots,
subtitles, or screenplay material is fetched or stored.
"""
from __future__ import annotations

import argparse
import fcntl
import re
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
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
    FilmGenre,
    FilmProvenance,
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


def fetch_rows(limit: int, offset: int = 0) -> list[dict[str, Any]]:
    # Keep independent relationships in separate queries. A single query would
    # multiply cast × genres × countries and becomes impractical at 1,000 films.
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": get_settings().wikidata_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }

    last_request_at = 0.0

    def run_query(query: str) -> list[dict[str, Any]]:
        nonlocal last_request_at
        pause = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request_at)
        if pause > 0:
            time.sleep(pause)
        with httpx.Client(timeout=90, headers=headers) as client:
            response = client.post(ENDPOINT, data={"query": query, "format": "json"})
        last_request_at = time.monotonic()
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            time.sleep(retry_after)
            return run_query(query)
        if response.status_code in {403, 401}:
            raise WikidataIngestionError(
                f"Wikidata denied the request (HTTP {response.status_code}); stopping rather than bypassing access controls."
            )
        response.raise_for_status()
        return response.json()["results"]["bindings"]

    film_rows = run_query(f"""
      SELECT ?film ?filmLabel ?releaseDate ?runtime WHERE {{
        {{ SELECT ?film WHERE {{ ?film wdt:P31 wd:Q11424; wdt:P364 wd:Q1860. }} LIMIT {limit} OFFSET {offset} }}
        OPTIONAL {{ ?film wdt:P577 ?releaseDate. }}
        OPTIONAL {{ ?film wdt:P2047 ?runtime. }}
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }}
    """)
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
        credit_rows = run_query(f"""
          SELECT ?film ?person ?personLabel ?role WHERE {{
            VALUES ?film {{ {values} }}
            {{ ?film wdt:P57 ?person. BIND("director" AS ?role) }}
            UNION {{ ?film wdt:P58 ?person. BIND("writer" AS ?role) }}
            UNION {{ ?film wdt:P161 ?person. BIND("cast" AS ?role) }}
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
          }}
        """)
        for row in [*genre_rows, *country_rows, *credit_rows]:
            header = by_film.get(item_id(_value(row, "film")))
            if header:
                enriched.append({**header, **row})
    return enriched


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
        genre = Genre(label=label, wikidata_id=wikidata_id)
        db.add(genre)
        db.flush()
    return genre


def ingest(db: Session, limit: int = 1000, offset: int = 0, rows: list[dict[str, Any]] | None = None) -> IngestionBatch:
    with exclusive_ingestion_lock():
        return _ingest_locked(db, limit, offset, rows)


def _ingest_locked(db: Session, limit: int, offset: int, rows: list[dict[str, Any]] | None) -> IngestionBatch:
    ensure_language_editions(db)
    source = source_for_wikidata(db)
    batch = IngestionBatch(source_id=source.id, external_reference=f"{ENDPOINT}?offset={offset}&limit={limit}", status="running")
    db.add(batch)
    db.flush()
    rows = fetch_rows(limit, offset) if rows is None else rows

    films: dict[str, dict[str, Any]] = defaultdict(lambda: {"genres": {}, "credits": {}, "countries": set()})
    for row in rows:
        film_qid = item_id(_value(row, "film"))
        title = clean_label(_value(row, "filmLabel"))
        if not film_qid or not title:
            continue
        record = films[film_qid]
        record.update({"title": title, "release_date": parse_date(_value(row, "releaseDate")), "runtime": _value(row, "runtime")})
        country = item_id(_value(row, "country"))
        if country:
            record["countries"].add(country)
        genre_qid, genre_label = item_id(_value(row, "genre")), clean_label(_value(row, "genreLabel"))
        if genre_qid and genre_label:
            record["genres"][genre_qid] = genre_label
        person_qid, person_label, role = item_id(_value(row, "person")), clean_label(_value(row, "personLabel")), _value(row, "role")
        if person_qid and person_label and role:
            record["credits"][(person_qid, role)] = person_label

    for film_qid, record in films.items():
        film = db.scalar(select(Film).where(Film.wikidata_id == film_qid))
        runtime = int(float(record["runtime"])) if record["runtime"] else None
        if not film:
            film = Film(
                canonical_title=record["title"], wikidata_id=film_qid, release_date=record["release_date"],
                runtime_minutes=runtime, original_language_code="en", country_codes=sorted(record["countries"]),
            )
            db.add(film)
            db.flush()
            db.add(FilmAlias(film_id=film.id, value=record["title"], normalized_value=normalize(record["title"]), language_code="en"))
            for field in ("canonical_title", "release_date", "runtime_minutes", "original_language_code", "country_codes"):
                db.add(FilmProvenance(film_id=film.id, source_id=source.id, batch_id=batch.id, field_name=field, source_reference=f"https://www.wikidata.org/wiki/{film_qid}"))
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
