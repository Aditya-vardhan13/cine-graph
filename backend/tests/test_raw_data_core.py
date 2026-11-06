import json
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CanonicalEntity, Claim, ClaimEvidence, DataSource, RawIngestionRun,
    RawIngestionRunSnapshot, SourceAssertion, SourceObject, SourceSnapshot,
)
from app.services import raw_snapshots
from app.services.wikidata_raw import (
    RawWikidataError,
    entitydata_url,
    entities_from_response,
    entity_from_entitydata,
    fetch_entities,
    ingest_entities,
    robots_allows,
    validate_entitydata_url,
    wikidata_entitydata_policy,
)
from app.services.wikidata_selection_resolution import WikidataDiscoveryUnavailable
from app.services.wikipedia_raw import page_lookup_record
from app.services.wikipedia_article_html import parse_article_html
from app.services.wikipedia_raw import ingest_captured_article
from app.services.evaluation_ingestion import qids_from_wikipedia_run
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_raw_snapshots_are_immutable_and_statements_are_replayable(tmp_path) -> None:
    engine = isolated_postgres_engine()
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
    retained_payload = json.dumps({"entities": {"Q42": entity}}, ensure_ascii=False).encode("utf-8")
    with Session(engine) as db:
        first = ingest_entities(
            db, {"Q42": entity}, raw_payloads={"Q42": retained_payload}, snapshot_root=tmp_path,
            robots_sha256="a" * 64, manifest_sha256="b" * 64,
        )
        missing_statement = db.scalar(select(SourceAssertion).where(SourceAssertion.source_property == "P57"))
        assert missing_statement is not None
        db.delete(missing_statement)
        db.commit()
        second = ingest_entities(
            db, {"Q42": entity}, raw_payloads={"Q42": retained_payload}, snapshot_root=tmp_path,
            robots_sha256="a" * 64, manifest_sha256="b" * 64,
        )
        stored = db.scalar(select(SourceSnapshot))
        assertions = list(db.scalars(select(SourceAssertion).order_by(SourceAssertion.statement_locator)))
        links = list(db.scalars(select(RawIngestionRunSnapshot).order_by(RawIngestionRunSnapshot.disposition)))
        runs = list(db.scalars(select(RawIngestionRun).order_by(RawIngestionRun.created_at)))

        assert first == {"objects": 1, "snapshots": 1, "source_assertions": 3}
        assert second == {"objects": 1, "snapshots": 0, "source_assertions": 1}
        assert stored.storage_uri and stored.storage_uri.startswith("file:")
        assert Path(urlparse(stored.storage_uri).path).read_bytes() == retained_payload
        assert json.loads(retained_payload)["entities"]["Q42"]["id"] == "Q42"
        assert sorted(item.disposition for item in links) == ["created", "reused"]
        assert len(runs) == 2 and all(run.manifest_hash == "b" * 64 for run in runs)
        assert [(item.source_property, item.statement_locator, item.source_rank) for item in assertions] == [
            ("P57", "claims.P57[0]", "preferred"), ("P577", "claims.P577[0]", "normal"),
            ("wikidata:label:en", "labels.en", None),
        ]
        assert assertions[-1].raw_value == {"language": "en", "text": "Fixture Film"}
        policy = wikidata_entitydata_policy(db, db.scalar(select(DataSource).where(DataSource.name == "Wikidata")))
        assert policy.decision == "allowed"
        assert policy.required_user_agent is True
        assert policy.robots_decision == "allow_extension_route"
        assert policy.allowed_paths == ["https://www.wikidata.org/wiki/Special:EntityData/*.json"]
        assert policy.policy_revision == f"robots-sha256:{'a' * 64}"
        assert policy.max_requests_per_minute <= 60
        assert policy.max_concurrency == 1


def test_wikidata_ingestion_requires_exact_upstream_response_bytes() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    entity = {"id": "Q42", "lastrevid": 123, "claims": {}}
    with Session(engine) as db:
        with pytest.raises(RawWikidataError, match="Exact EntityData response bytes are required"):
            ingest_entities(db, {"Q42": entity})
        assert db.scalar(select(RawIngestionRun)) is None


def test_captured_wikipedia_article_persists_exact_response_without_refetch(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    payload = (Path(__file__).parent / "fixtures" / "wikipedia-article-html-slice-v1.html").read_bytes()
    canonical_url = "https://en.wikipedia.org/wiki/Example_film"
    document = parse_article_html(payload, canonical_url=canonical_url)

    with Session(engine) as db:
        result = ingest_captured_article(
            db, payload=payload, canonical_url=canonical_url,
            media_type="text/html", expected_qid=document.metadata.wikidata_id,
            robots_sha256="c" * 64, manifest_sha256="d" * 64,
            storage_root=tmp_path,
        )
        stored = db.scalar(select(SourceSnapshot))
        assertions = list(db.scalars(select(SourceAssertion)))
        run = db.scalar(select(RawIngestionRun))

        assert result["resolved"] == 1
        assert result["snapshots"] == 1
        assert stored is not None and stored.source_revision == str(document.metadata.revision_id)
        assert Path(urlparse(stored.storage_uri).path).read_bytes() == payload
        assert stored.content_hash == sha256(payload).hexdigest()
        assert assertions
        assert run is not None and run.manifest_hash == "d" * 64


def test_title_discovery_stays_disabled_without_permitted_route() -> None:
    with pytest.raises(WikidataDiscoveryUnavailable, match="title search is disabled"):
        from app.services.wikidata_selection_resolution import search_ids
        search_ids("The Dark Knight")

    assert callable(fetch_entities)


def test_normalized_claim_requires_a_retained_source_assertion() -> None:
    engine = isolated_postgres_engine()
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


def test_wikidata_entitydata_parser_uses_requested_pinned_item() -> None:
    # Field-minimized parser fixture from the retained Q5815826 EntityData
    # response at revision 2530451875 (full response remains local/ignored).
    fixture = Path(__file__).parent / "fixtures/wikidata-entitydata-response-slice-v1.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    entity = entity_from_entitydata(payload, "Q5815826")

    assert entity["id"] == "Q5815826"
    assert entity["lastrevid"] == 2530451875
    assert entity["labels"]["en"]["value"] == "Coco"

    with pytest.raises(RawWikidataError, match="did not contain the requested revisioned entity"):
        entity_from_entitydata(payload, "Q123")


def test_wikidata_entitydata_url_is_constrained_to_known_qid_json_route() -> None:
    assert entitydata_url("Q163872") == "https://www.wikidata.org/wiki/Special:EntityData/Q163872.json"
    assert validate_entitydata_url("https://www.wikidata.org/wiki/Special:EntityData/Q163872.json") == entitydata_url("Q163872")
    for url in (
        "http://www.wikidata.org/wiki/Special:EntityData/Q163872.json",
        "https://www.wikidata.org/w/api.php?action=wbgetentities",
        "https://www.wikidata.org/wiki/Special:EntityData/Q163872.json?revision=1",
        "https://www.wikidata.org.evil.example/wiki/Special:EntityData/Q163872.json",
        "https://www.wikidata.org/wiki/Special:EntityData/../Q163872.json",
    ):
        with pytest.raises(RawWikidataError):
            validate_entitydata_url(url)
    with pytest.raises(RawWikidataError, match="valid QID"):
        entitydata_url("not-a-qid")


def test_wikidata_robots_specific_allow_overrides_broader_encoded_disallows() -> None:
    # Rules mirror the relevant current Wikidata robots.txt exception:
    # the entity-data JSON suffix is allowed, while the Special namespace stays
    # denied for other paths. Reserved colon comparison follows RFC 9309.
    rules = """User-agent: *
Disallow: /wiki/Special:
Disallow: /wiki/Special%3A
Disallow: /wiki/Special:EntityData/


Allow: /wiki/Special:EntityData/*.
"""
    assert robots_allows(
        rules, user_agent="CineGraphResearch/1.0 (contact: test@example.org)",
        url="https://www.wikidata.org/wiki/Special:EntityData/Q163872.json",
    ) is True
    assert robots_allows(
        rules, user_agent="CineGraphResearch/1.0", url="https://www.wikidata.org/wiki/Special:EntityData/Q163872",
    ) is False
    assert robots_allows(
        rules, user_agent="CineGraphResearch/1.0", url="https://www.wikidata.org/wiki/Special:Other/Q163872.json",
    ) is False


def test_wikidata_robots_uses_exact_agent_group_before_wildcard() -> None:
    rules = """User-agent: *
Allow: /wiki/Special:EntityData/*.

User-agent: CineGraphResearch
Disallow: /wiki/Special:EntityData/
"""
    assert robots_allows(
        rules, user_agent="CineGraphResearch/1.0", url="https://www.wikidata.org/wiki/Special:EntityData/Q163872.json",
    ) is False


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
