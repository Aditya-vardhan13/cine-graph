import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Assertion, CanonicalEntity
from app.services.classify_work_targets import apply_classifications, classify_targets
from app.services.wikidata import upsert_genre
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_classification_uses_supported_type_and_unblocks_only_typed_assertions() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        film = CanonicalEntity(entity_kind="film", canonical_label="Film", wikidata_id="Q1")
        target = CanonicalEntity(entity_kind="unknown_work", canonical_label="Q2", wikidata_id="Q2")
        db.add_all([film, target])
        db.flush()
        db.add(Assertion(
            subject_entity_id=film.id, predicate="based_on", object_entity_id=target.id,
            object_entity_kind="unknown_work", value_json=None, assertion_kind="source_fact",
            review_status="review_required",
        ))
        db.commit()

        stats = apply_classifications(db, {"Q2": ("book", "Fixture Novel")})
        assertion = db.scalar(select(Assertion))
        target = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == "Q2"))

        assert stats == {"classified": 1, "films_imported": 0, "remaining_unknown": 0}
        assert target is not None and (target.entity_kind, target.canonical_label) == ("book", "Fixture Novel")
        assert assertion is not None and (assertion.object_entity_kind, assertion.review_status) == ("book", "resolved")


def test_classifier_selects_a_deterministic_type_when_wikidata_returns_multiple_ancestors() -> None:
    rows = [
        {"target": {"value": "http://www.wikidata.org/entity/Q2"}, "targetLabel": {"value": "Fixture"}, "kind": {"value": "book"}},
        {"target": {"value": "http://www.wikidata.org/entity/Q2"}, "targetLabel": {"value": "Fixture"}, "kind": {"value": "film"}},
    ]
    assert classify_targets(["Q2"], runner=lambda _query: rows) == {"Q2": ("film", "Fixture")}


def test_genre_projection_reuses_an_existing_label_for_a_second_wikidata_item() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = upsert_genre(db, "Q100", "melodrama")
        second = upsert_genre(db, "Q101", "melodrama")
        db.commit()
        assert first.id == second.id


def test_empty_classification_retries_already_typed_film_targets() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source_film = CanonicalEntity(entity_kind="film", canonical_label="Source", wikidata_id="Q1")
        target_film = CanonicalEntity(entity_kind="film", canonical_label="Target", wikidata_id="Q2")
        db.add_all([source_film, target_film])
        db.flush()
        db.add(Assertion(
            subject_entity_id=source_film.id, predicate="follows", object_entity_id=target_film.id,
            object_entity_kind="film", assertion_kind="source_fact", review_status="resolved",
        ))
        db.commit()

        stats = apply_classifications(db, {}, fetcher=lambda _qids: [])
        assert stats == {"classified": 0, "films_imported": 0, "remaining_unknown": 0}
