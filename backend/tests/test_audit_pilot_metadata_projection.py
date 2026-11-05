import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Assertion,
    AssertionEvidence,
    CanonicalEntity,
    DataSource,
    SourceAssertion,
    SourceObject,
    SourceSnapshot,
)
from scripts.audit_pilot_metadata_projection import source_evidence_by_assertion
from tests.postgres_test_db import isolated_postgres_engine


@pytest.mark.integration
def test_metadata_audit_follows_assertion_to_raw_value_and_snapshot(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    payload = b'{"statement":"runtime"}'
    digest = hashlib.sha256(payload).hexdigest()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_bytes(payload)
    with Session(engine) as db:
        source = DataSource(
            name="Metadata audit fixture",
            url="https://example.test/source",
            source_type="recorded_test_fixture",
            license="CC0 1.0",
            rights_status="open",
        )
        entity = CanonicalEntity(entity_kind="film", canonical_label="Fixture film")
        db.add_all([source, entity])
        db.flush()
        source_object = SourceObject(
            source_id=source.id,
            external_id="fixture:runtime",
            object_kind="film",
            canonical_url="https://example.test/film",
        )
        db.add(source_object)
        db.flush()
        snapshot = SourceSnapshot(
            source_object_id=source_object.id,
            canonical_url=source_object.canonical_url,
            source_revision="fixture-revision-7",
            retrieved_at=datetime(2026, 11, 4, 12, 30, tzinfo=timezone.utc),
            content_hash=digest,
            byte_size=len(payload),
            storage_uri=snapshot_path.as_uri(),
            license="CC0 1.0",
            attribution_url="https://example.test/attribution",
        )
        db.add(snapshot)
        db.flush()
        raw = SourceAssertion(
            source_snapshot_id=snapshot.id,
            statement_locator="claims.P2047[1]",
            source_property="P2047",
            raw_subject={"wikidata_id": "Q123"},
            raw_value={"amount": "+148", "unit": "minute"},
            raw_qualifiers={"P518": [{"id": "Q26225765"}]},
            extractor_version="fixture-extractor-v2",
        )
        assertion = Assertion(
            subject_entity_id=entity.id,
            predicate="runtime",
            value_json={"minutes": 148},
            qualifiers={"P518": [{"id": "Q26225765"}]},
            assertion_kind="source_fact",
            source_id=source.id,
            source_reference="https://example.test/film#runtime",
            source_revision=snapshot.source_revision,
            review_status="resolved",
        )
        db.add_all([raw, assertion])
        db.flush()
        evidence = AssertionEvidence(
            assertion_id=assertion.id,
            source_assertion_id=raw.id,
            evidence_type="source_assertion",
            reference="https://example.test/film#claims.P2047[1]",
        )
        db.add(evidence)
        db.flush()

        result = source_evidence_by_assertion(db, [entity.id])

        assert set(result) == {assertion.id}
        assert result[assertion.id] == [{
            "evidence_id": str(evidence.id),
            "source_assertion_id": str(raw.id),
            "evidence_type": "source_assertion",
            "reference": "https://example.test/film#claims.P2047[1]",
            "note": None,
            "statement_locator": "claims.P2047[1]",
            "source_property": "P2047",
            "raw_value": {"amount": "+148", "unit": "minute"},
            "raw_qualifiers": {"P518": [{"id": "Q26225765"}]},
            "extractor_version": "fixture-extractor-v2",
            "snapshot_id": str(snapshot.id),
            "snapshot_url": "https://example.test/film",
            "snapshot_revision": "fixture-revision-7",
            "snapshot_retrieved_at": "2026-11-04T12:30:00+00:00",
            "snapshot_fetch_status": "success",
            "snapshot_attribution_url": "https://example.test/attribution",
            "snapshot_hash": digest,
            "snapshot_byte_size": len(payload),
            "snapshot_storage_uri": snapshot_path.as_uri(),
            "snapshot_integrity_status": "verified",
            "snapshot_license": "CC0 1.0",
        }]
    engine.dispose()
