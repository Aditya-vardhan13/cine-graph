import json
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CanonicalEntity, Claim, ClaimEvidence, DataSource, RawIngestionRun,
    RawIngestionRunSnapshot, SourceAssertion, SourceObject, SourceSnapshot,
)
from app.services import raw_snapshots
from app.services.wikidata_raw import entities_from_response, ingest_entities, wikidata_api_policy
from app.services.wikipedia_raw import page_lookup_record
from app.services.evaluation_ingestion import qids_from_wikipedia_run


def test_raw_snapshots_are_immutable_and_statements_are_replayable(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    entity = {
        "id": "Q42",
        "lastrevid": 123,
        "labels": {"en": {"value": "Fixture Film"}},
        "claims": {
            "P577": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": "+2020-01-01T00:00:00Z", "type": "time"}}, "rank": "normal"}],
            "P57": [{"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q10"}, "type": "wikibase-entityid"}}, "rank": "preferred"}],
        },
    }
    with Session(engine) as db:
        first = ingest_entities(db, {"Q42": entity}, snapshot_root=tmp_path)
        second = ingest_entities(db, {"Q42": entity}, snapshot_root=tmp_path)
        stored = db.scalar(select(SourceSnapshot))
        assertions = list(db.scalars(select(SourceAssertion).order_by(SourceAssertion.statement_locator)))
        links = list(db.scalars(select(RawIngestionRunSnapshot).order_by(RawIngestionRunSnapshot.disposition)))

        assert first == {"objects": 1, "snapshots": 1, "source_assertions": 2}
        assert second == {"objects": 1, "snapshots": 0, "source_assertions": 0}
        assert stored.storage_uri and stored.storage_uri.startswith("file:")
        assert json.loads(Path(urlparse(stored.storage_uri).path).read_text())["id"] == "Q42"
        assert sorted(item.disposition for item in links) == ["created", "reused"]
        assert [(item.source_property, item.statement_locator, item.source_rank) for item in assertions] == [
            ("P577", "claims.P577[0]", "normal"), ("P57", "claims.P57[0]", "preferred"),
        ]
        policy = wikidata_api_policy(db, db.scalar(select(DataSource).where(DataSource.name == "Wikidata")))
        assert policy.decision == "allowed"
        assert policy.required_user_agent is True


def test_normalized_claim_requires_a_retained_source_assertion() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = DataSource(name="Fixture", url="https://fixture.test", source_type="metadata", license="CC0", rights_status="open")
        entity = CanonicalEntity(entity_kind="film", canonical_label="Fixture film")
        db.add_all([source, entity])
        db.flush()
        run = RawIngestionRun(source_id=source.id, adapter_name="fixture", adapter_version="1", status="complete")
        obj = SourceObject(source_id=source.id, external_id="fixture-1", object_kind="film", canonical_url="https://fixture.test/1")
        db.add_all([run, obj])
        db.flush()
        snap = SourceSnapshot(source_object_id=obj.id, ingestion_run_id=run.id, canonical_url=obj.canonical_url, content_hash="a" * 64, license="CC0")
        db.add(snap)
        db.flush()
        raw = SourceAssertion(source_snapshot_id=snap.id, statement_locator="fixture.release", raw_subject={}, raw_value={"year": 2020}, raw_qualifiers={}, extractor_version="1")
        claim = Claim(subject_entity_id=entity.id, predicate="release_event", value_json={"year": 2020}, normalization_version="1", status="resolved")
        db.add_all([raw, claim])
        db.flush()
        db.add(ClaimEvidence(claim_id=claim.id, source_assertion_id=raw.id))
        db.commit()

        assert db.scalar(select(ClaimEvidence)) is not None


def test_wikidata_response_parser_accepts_the_api_entity_dictionary() -> None:
    assert entities_from_response({"entities": {"Q42": {"id": "Q42", "claims": {}}}}) == {
        "Q42": {"id": "Q42", "claims": {}},
    }


def test_wikipedia_page_record_preserves_resolved_page_shape() -> None:
    class Page:
        title = "Fixture Film"
        pageid = 42
        fullurl = "https://en.wikipedia.org/wiki/Fixture_Film"
        sections = [type("Section", (), {"title": "Plot"})(), type("Section", (), {"title": "Cast"})()]

        def exists(self) -> bool:
            return True

    assert page_lookup_record("Fixture Film", Page()) == {
        "requested_title": "Fixture Film", "resolved_title": "Fixture Film", "pageid": 42,
        "fullurl": "https://en.wikipedia.org/wiki/Fixture_Film", "section_titles": ["Plot", "Cast"],
    }
