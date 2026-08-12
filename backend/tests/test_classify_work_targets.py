from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Assertion, CanonicalEntity
from app.services.classify_work_targets import apply_classifications, classify_targets


def test_classification_uses_supported_type_and_unblocks_only_typed_assertions() -> None:
    engine = create_engine("sqlite://")
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
