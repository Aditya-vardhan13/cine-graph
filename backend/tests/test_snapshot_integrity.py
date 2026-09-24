import hashlib

import pytest
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Assertion, AssertionEvidence, CanonicalEntity, DataSource, SourceAssertion,
    SourceObject, SourceSnapshot,
)
from app.services.snapshot_integrity import audit_snapshots
from app.services.snapshot_integrity import verify_snapshot_file
from tests.postgres_test_db import isolated_postgres_engine


def test_snapshot_file_requires_matching_bytes_and_size(tmp_path) -> None:
    payload = b'{"source":"retained"}'
    path = tmp_path / "source.json"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    assert verify_snapshot_file(path.as_uri(), digest, len(payload)) == "verified"
    assert verify_snapshot_file(path.as_uri(), "0" * 64, len(payload)) == "hash_mismatch"
    assert verify_snapshot_file(path.as_uri(), digest, len(payload) + 1) == "size_mismatch"


def test_snapshot_file_reports_missing_or_unsupported_source(tmp_path) -> None:
    assert verify_snapshot_file(None, "0" * 64, None) == "no_uri"
    assert verify_snapshot_file((tmp_path / "missing.json").as_uri(), "0" * 64, None) == "missing"
    assert verify_snapshot_file("s3://bucket/source.json", "0" * 64, None) == "unsupported_uri"


@pytest.mark.integration
def test_audit_groups_real_postgres_snapshot_records(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    payload = b'{"source":"retained"}'
    path = tmp_path / "retained.json"
    path.write_bytes(payload)
    with Session(engine) as db:
        source = DataSource(
            name="Fixture source", url="https://example.org", source_type="fixture",
            license="CC0", rights_status="reusable",
        )
        db.add(source)
        db.flush()
        item = SourceObject(
            source_id=source.id, external_id="fixture:1", object_kind="film",
            canonical_url="https://example.org/1",
        )
        db.add(item)
        db.flush()
        retained = SourceSnapshot(
                source_object_id=item.id, source_revision="1", canonical_url=item.canonical_url,
                content_hash=hashlib.sha256(payload).hexdigest(), byte_size=len(payload),
                storage_uri=path.as_uri(), license="CC0",
            )
        missing = SourceSnapshot(
                source_object_id=item.id, source_revision="2", canonical_url=item.canonical_url,
                content_hash="0" * 64, storage_uri=(tmp_path / "lost.json").as_uri(), license="CC0",
            )
        entity = CanonicalEntity(canonical_label="Fixture film", entity_kind="film")
        db.add_all([retained, missing, entity])
        db.flush()
        raw = SourceAssertion(
            source_snapshot_id=missing.id, statement_locator="claims.P31[0]",
            source_property="P31", raw_subject={"wikidata_id": "Q1"},
            raw_value={"value": "Q11424"}, raw_qualifiers={}, extractor_version="fixture-v1",
        )
        published = Assertion(
            subject_entity_id=entity.id, predicate="instance_of", value_json={"wikidata_id": "Q11424"},
            qualifiers={}, assertion_kind="source_fact", review_status="resolved",
        )
        db.add_all([raw, published])
        db.flush()
        db.add(AssertionEvidence(
            assertion_id=published.id, source_assertion_id=raw.id,
            evidence_type="source_assertion", reference="https://example.org/1",
        ))
        db.commit()
        report = audit_snapshots(db, source_name="Fixture source", sample_limit=1)

    assert report["total"] == 2
    assert report["sources"]["Fixture source"]["counts"] == {"verified": 1, "missing": 1}
    assert len(report["sources"]["Fixture source"]["examples"]["missing"]) == 1
    assert report["sources"]["Fixture source"]["explicitly_linked_assertions_with_unavailable_source"] == {"resolved": 1}
