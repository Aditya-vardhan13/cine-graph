"""Verify exact source identity and story matching in isolated PostgreSQL."""
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CanonicalEntity, DataSource, NarrativePassage, SourceAssertion, SourceObject, SourceSnapshot
from app.services.wikipedia_article_html import parse_article_html
from scripts.prepare_same_revision_refresh import prepare
from tests.postgres_test_db import isolated_postgres_engine


def test_same_revision_refresh_requires_exact_identity_and_story():
    directory = Path("data/evaluation/writer-source-audit/wikipedia-refresh-v1")
    checkpoint = directory / "checkpoint.json"
    if not checkpoint.exists():
        pytest.skip("retained local article unavailable")
    qid = "Q578595"
    capture = json.loads(checkpoint.read_bytes())["captures"][qid]
    path = directory / "snapshots" / f"{capture['sha256']}.html"
    payload = path.read_bytes()
    doc = parse_article_html(payload, canonical_url=capture["canonical_url"], expected_qid=qid)
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        entity = CanonicalEntity(entity_kind="film", canonical_label=doc.metadata.title, wikidata_id=qid)
        source = DataSource(name="English Wikipedia", url="https://en.wikipedia.org/", source_type="wiki",
                            license="CC BY-SA 4.0", rights_status="attributed_reuse")
        db.add_all([entity, source]); db.flush()
        obj = SourceObject(source_id=source.id, external_id=f"enwiki:{doc.metadata.page_id}",
                           object_kind="wiki_page", canonical_url=doc.metadata.canonical_url)
        db.add(obj); db.flush()
        snapshot = SourceSnapshot(source_object_id=obj.id, source_revision=str(doc.metadata.revision_id),
                                  canonical_url=obj.canonical_url, content_hash=hashlib.sha256(payload).hexdigest(),
                                  byte_size=len(payload), storage_uri=path.resolve().as_uri(), license="CC BY-SA 4.0",
                                  fetch_status="success", parser_version="enwiki-article-html-capture-v1")
        db.add(snapshot); db.flush()
        db.add(SourceAssertion(source_snapshot_id=snapshot.id, statement_locator="qid", source_property="wikidata_item",
                               raw_subject={}, raw_value={"wikidata_id": qid}, raw_qualifiers={}, extractor_version="test"))
        for p in doc.passages:
            if p.section_locator == "plot":
                db.add(NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=snapshot.id,
                                        section_locator="plot", section_title="Plot", ordinal=p.ordinal,
                                        content=p.content, content_hash=p.content_hash, citation_markers=[],
                                        extraction_version="enwiki-article-html-extraction-v7"))
        db.commit()
        kwargs = dict(qid=qid, capture=capture, payload=payload, expected_snapshot_id=snapshot.id,
                      expected_snapshot_hash=snapshot.content_hash)
        result = prepare(db, **kwargs)
        assert result["prior_snapshot_id"] == str(snapshot.id)
        assert result["story_comparison"] == "nfc-whitespace-exact-v1"
        assert result["section_coverage_check"] == "minimum-75-percent-characters-v1"
        assert result["rights_status"] == "review_required" and result["product_ingested"] is False
        with pytest.raises(ValueError, match="identity, revision or integrity"):
            prepare(db, **{**kwargs, "expected_snapshot_hash": "0" * 64})
        passage = db.query(NarrativePassage).filter_by(subject_entity_id=entity.id).first()
        passage.content += " altered"
        passage.content_hash = hashlib.sha256(passage.content.encode()).hexdigest()
        db.flush()
        with pytest.raises(ValueError, match="Story text differs"):
            prepare(db, **kwargs)
        db.rollback()
        db.add(NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=snapshot.id,
                                section_locator="legacy-table-only", section_title="Legacy table",
                                ordinal=0, content="A table of awards", content_hash=hashlib.sha256(b"A table of awards").hexdigest(),
                                citation_markers=[], extraction_version="enwiki-article-html-extraction-v7"))
        db.flush()
        with pytest.raises(ValueError, match="Section coverage reduced.*legacy-table-only"):
            prepare(db, **kwargs)
        db.rollback()
    engine.dispose()
