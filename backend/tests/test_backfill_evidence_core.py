from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Assertion, CanonicalEntity, DataSource, ExternalWorkRelationship, Film,
    FilmAlias, FilmCredit, LanguageEdition, Person,
)
from app.services.backfill_evidence_core import backfill


def test_backfill_is_idempotent_and_keeps_external_targets_typed_unknown() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", native_name="English", script="Latin", enabled=True, status="live"))
        source = DataSource(name="Fixture source", url="https://example.test", source_type="metadata", license="CC0", rights_status="open")
        db.add(source)
        db.flush()
        film = Film(canonical_title="Fixture Film", original_language_code="en", country_codes=[], wikidata_id="Q10")
        person = Person(canonical_name="Fixture Writer", wikidata_id="Q11")
        db.add_all([film, person])
        db.flush()
        db.add_all([
            FilmAlias(film_id=film.id, value="Fixture Film", normalized_value="fixture film", language_code="en"),
            FilmCredit(film_id=film.id, person_id=person.id, role="writer", source_id=source.id, source_reference="https://example.test/Q10"),
            ExternalWorkRelationship(from_film_id=film.id, to_wikidata_id="Q12", relationship_type="based_on", source_id=source.id, source_reference="https://example.test/Q10"),
        ])
        db.commit()

        first = backfill(db)
        second = backfill(db)
        film = db.scalar(select(Film).where(Film.wikidata_id == "Q10"))
        target = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == "Q12"))
        assertions = list(db.scalars(select(Assertion)))

        assert first["entities"] == 3
        assert second == {"entities": 0, "aliases": 0, "source_records": 0, "assertions": 0}
        assert film is not None and film.entity_id is not None
        assert target is not None and target.entity_kind == "unknown_work"
        assert {(item.predicate, item.object_entity_kind, item.review_status) for item in assertions} == {
            ("writer", "person", "resolved"), ("based_on", "unknown_work", "review_required")
        }
