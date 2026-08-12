from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Assertion, CanonicalEntity, EntityAlias, InsightCard, InsightEvidence


def test_typed_assertions_and_language_aliases_preserve_evidence_boundaries() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        film = CanonicalEntity(entity_kind="film", canonical_label="Example Film", wikidata_id="Q1")
        book = CanonicalEntity(entity_kind="book", canonical_label="Example Novel", wikidata_id="Q2")
        db.add_all([film, book])
        db.flush()
        db.add_all([
            EntityAlias(
                entity_id=film.id, value="Example Film", normalized_value="example film",
                language_code="en", script="Latin", alias_kind="title",
            ),
            EntityAlias(
                entity_id=film.id, value="ఉదాహరణ చిత్రం", normalized_value="ఉదాహరణ చిత్రం",
                language_code="te", script="Telugu", alias_kind="title",
            ),
            Assertion(
                subject_entity_id=film.id, predicate="based_on", source_property="P144",
                object_entity_id=book.id, object_entity_kind="book", assertion_kind="source_fact",
                review_status="published",
            ),
        ])
        db.commit()

        assertion = db.query(Assertion).one()
        assert assertion.object_entity is not None
        assert assertion.object_entity.entity_kind == "book"
        assert {alias.language_code for alias in film.aliases} == {"en", "te"}


def test_assertions_and_insight_evidence_cannot_be_targetless() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        entity = CanonicalEntity(entity_kind="film", canonical_label="Example Film")
        db.add(entity)
        db.flush()
        db.add(Assertion(subject_entity_id=entity.id, predicate="follows"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("targetless assertions must violate the evidence contract")

        insight = InsightCard(
            kind="creative_engine", title="Fixture", writer_question="What persists?",
            explanation="A fixture.", subject_entity_id=entity.id,
        )
        db.add(insight)
        db.flush()
        db.add(InsightEvidence(insight_id=insight.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("targetless insight evidence must violate the evidence contract")
