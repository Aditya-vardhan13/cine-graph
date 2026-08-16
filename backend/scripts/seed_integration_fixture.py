"""Reset and seed the isolated CineGraph integration database.

This command is intentionally unable to operate on a non-test database.  It
creates a tiny, source-backed catalogue that exercises the public API without
touching the user's local research corpus or calling external services.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import inspect, text

from app.db import SessionLocal, engine
from app.models import (
    Assertion,
    CanonicalEntity,
    DataSource,
    Film,
    FilmCredit,
    FilmGenre,
    FilmProvenance,
    Genre,
    IngestionBatch,
    LanguageEdition,
    Person,
)


def require_test_database() -> None:
    database = engine.url.database or ""
    if not database.endswith("_test"):
        raise RuntimeError(f"Refusing to reset non-test database: {database!r}")


def reset_database() -> None:
    require_test_database()
    table_names = inspect(engine).get_table_names()
    if not table_names:
        return
    quoted = ", ".join(f'"{name}"' for name in table_names if name != "alembic_version")
    if quoted:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


def seed() -> None:
    reset_database()
    with SessionLocal() as db:
        english = LanguageEdition(
            code="en", display_name="English", native_name="English", script="Latin", enabled=True, status="live",
        )
        source = DataSource(
            name="Integration fixture source",
            url="https://example.test/cinegraph-fixture",
            source_type="recorded_test_fixture",
            license="CC0 1.0",
            rights_status="open",
            notes="Deterministic local integration fixture; no external request.",
        )
        db.add_all([english, source])
        db.flush()
        batch = IngestionBatch(source_id=source.id, external_reference="integration-fixture-v1", records_received=2, records_published=2)
        begins_entity = CanonicalEntity(entity_kind="film", canonical_label="Batman Begins", wikidata_id="Q166262")
        knight_entity = CanonicalEntity(entity_kind="film", canonical_label="The Dark Knight", wikidata_id="Q163872")
        nolan_entity = CanonicalEntity(entity_kind="person", canonical_label="Christopher Nolan", wikidata_id="Q25191")
        db.add_all([batch, begins_entity, knight_entity, nolan_entity])
        db.flush()

        begins = Film(
            canonical_title="Batman Begins", release_date=date(2005, 6, 15), runtime_minutes=140,
            original_language_code="en", country_codes=["US", "GB"], wikidata_id="Q166262", entity_id=begins_entity.id,
        )
        knight = Film(
            canonical_title="The Dark Knight", release_date=date(2008, 7, 18), runtime_minutes=152,
            original_language_code="en", country_codes=["US", "GB"], wikidata_id="Q163872", entity_id=knight_entity.id,
        )
        nolan = Person(canonical_name="Christopher Nolan", wikidata_id="Q25191", entity_id=nolan_entity.id)
        crime = Genre(label="crime film", wikidata_id="Q959790")
        db.add_all([begins, knight, nolan, crime])
        db.flush()
        reference = "https://www.wikidata.org/wiki/Q163872"
        db.add_all([
            FilmGenre(film_id=begins.id, genre_id=crime.id, source_id=source.id, source_reference=reference),
            FilmGenre(film_id=knight.id, genre_id=crime.id, source_id=source.id, source_reference=reference),
            FilmCredit(film_id=begins.id, person_id=nolan.id, role="director", source_id=source.id, source_reference=reference),
            FilmCredit(film_id=knight.id, person_id=nolan.id, role="director", source_id=source.id, source_reference=reference),
            FilmProvenance(film_id=begins.id, source_id=source.id, batch_id=batch.id, field_name="canonical_title", source_reference="https://www.wikidata.org/wiki/Q166262"),
            FilmProvenance(film_id=knight.id, source_id=source.id, batch_id=batch.id, field_name="canonical_title", source_reference=reference),
            Assertion(
                subject_entity_id=begins_entity.id, object_entity_id=knight_entity.id, object_entity_kind="film",
                predicate="followed_by", assertion_kind="source_fact", source_id=source.id,
                source_reference=reference, review_status="published",
            ),
        ])
        db.commit()


if __name__ == "__main__":
    seed()
