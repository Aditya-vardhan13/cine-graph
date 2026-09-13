from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Assertion,
    AssertionEvidence,
    CanonicalEntity,
    DataSource,
    LanguageEdition,
    RawIngestionRun,
    ReferenceCollection,
    ReferenceCollectionMembership,
    SourceAssertion,
    SourceObject,
    SourceSnapshot,
)
from app.services.source_assertion_projection import project_source_assertions, projection_coverage
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def raw_entity(qid: str) -> dict:
    return {
        "snaktype": "value",
        "datavalue": {"type": "wikibase-entityid", "value": {"id": qid}},
    }


def raw_time(value: str) -> dict:
    return {
        "snaktype": "value",
        "datavalue": {"type": "time", "value": {"time": value, "precision": 11}},
    }


def add_statement(db: Session, snapshot_id, locator: str, prop: str, value: dict) -> None:
    db.add(SourceAssertion(
        source_snapshot_id=snapshot_id,
        statement_locator=locator,
        source_property=prop,
        raw_subject={"wikidata_id": "Q42", "label": "Fixture Film"},
        raw_value=value,
        raw_qualifiers={},
        source_rank="normal",
        extractor_version="fixture-v1",
    ))


def test_projector_is_idempotent_evidence_linked_and_retracts_old_snapshots() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(
            code="en", display_name="English", native_name="English", script="Latin",
            enabled=True, status="live",
        ))
        source = DataSource(
            name="Wikidata", url="https://www.wikidata.org/", source_type="structured",
            license="CC0 1.0", rights_status="open",
        )
        subject = CanonicalEntity(entity_kind="film", canonical_label="Fixture Film", wikidata_id="Q42")
        collection = ReferenceCollection(
            code="fixture-films", title="Fixture films", description="Integration fixture",
            language_code="en", selection_method="fixture", selection_version="1",
        )
        db.add_all([source, subject, collection])
        db.flush()
        db.add(ReferenceCollectionMembership(
            collection_code=collection.code, entity_id=subject.id, selection_position=1,
            selection_signals={}, source_reference="https://fixture.test/selection",
        ))
        run = RawIngestionRun(
            source_id=source.id, adapter_name="fixture", adapter_version="1", status="complete",
        )
        source_object = SourceObject(
            source_id=source.id, external_id="Q42", object_kind="wikibase_item",
            canonical_url="https://www.wikidata.org/wiki/Q42",
        )
        db.add_all([run, source_object])
        db.flush()
        old_snapshot = SourceSnapshot(
            source_object_id=source_object.id, ingestion_run_id=run.id, source_revision="1",
            canonical_url=source_object.canonical_url, content_hash="a" * 64, license="CC0 1.0",
            retrieved_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(old_snapshot)
        db.flush()
        add_statement(db, old_snapshot.id, "claims.P57[0]", "P57", raw_entity("Q10"))
        db.commit()

        first = project_source_assertions(db, collection_code=collection.code, batch_size=1)
        assert first["assertions_created"] == 1

        new_snapshot = SourceSnapshot(
            source_object_id=source_object.id, ingestion_run_id=run.id, source_revision="2",
            canonical_url=source_object.canonical_url, content_hash="b" * 64, license="CC0 1.0",
            retrieved_at=datetime.now(timezone.utc),
        )
        db.add(new_snapshot)
        db.flush()
        add_statement(db, new_snapshot.id, "claims.P57[0]", "P57", raw_entity("Q11"))
        add_statement(db, new_snapshot.id, "claims.P144[0]", "P144", raw_entity("Q99"))
        add_statement(db, new_snapshot.id, "claims.P577[0]", "P577", raw_time("+2008-07-18T00:00:00Z"))
        add_statement(db, new_snapshot.id, "claims.P999[0]", "P999", raw_entity("Q88"))
        db.commit()

        second = project_source_assertions(db, collection_code=collection.code, batch_size=2)
        third = project_source_assertions(db, collection_code=collection.code, batch_size=2)
        assertions = list(db.scalars(select(Assertion).order_by(Assertion.created_at, Assertion.predicate)))
        evidence = list(db.scalars(select(AssertionEvidence).where(
            AssertionEvidence.source_assertion_id.is_not(None),
        )))
        targets = {
            entity.wikidata_id: entity.entity_kind
            for entity in db.scalars(select(CanonicalEntity).where(
                CanonicalEntity.wikidata_id.in_(("Q10", "Q11", "Q99")),
            ))
        }
        coverage = projection_coverage(db, collection.code)

        assert second["assertions_created"] == 3
        assert second["assertions_retracted"] == 1
        assert second["skipped_by_property"] == {"P999": 1}
        assert third["assertions_created"] == 0
        assert third["assertions_reused"] == 3
        assert len(evidence) == 4
        assert targets == {"Q10": "person", "Q11": "person", "Q99": "unknown_work"}
        active = {(item.predicate, item.object_entity_kind, item.review_status) for item in assertions if item.review_status != "retracted"}
        assert active == {
            ("director", "person", "resolved"),
            ("based_on", "unknown_work", "review_required"),
            ("release_event", None, "resolved"),
        }
        assert coverage["raw_linked_coverage_percent"] == 100.0
        assert coverage["reviewed_coverage_percent"] == 100.0
