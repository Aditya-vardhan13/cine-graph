import hashlib
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    DataSource,
    EvidenceChunk,
    LanguageEdition,
    NarrativePassage,
    RawIngestionRun,
    ReferenceCollection,
    ReferenceCollectionMembership,
    SourceAccessPolicy,
    SourceAssertion,
    SourceSnapshot,
)
from app.services.wikipedia_article_html import parse_article_html
from app.services.wikipedia_raw import (
    ADAPTER_VERSION,
    persist_article_snapshot,
    source_for_wikipedia,
    wikipedia_article_html_policy,
)
from app.services.wikipedia_research import ARTICLE_HTML_EXTRACTION_VERSION, extract_passages
from app.services.current_narrative_passages import current_passage_rows
from app.services.movie_intake_worker import has_plot
from app.services.evidence_preprocessing import (
    ChunkConfiguration,
    build_evidence_chunks,
    evidence_chunk_quality_report,
)
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "wikipedia-article-html-slice-v1.html"
ARTICLE_URL = "https://en.wikipedia.org/wiki/The_Dark_Knight"


def test_article_snapshot_and_passages_keep_revision_provenance(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    payload = FIXTURE.read_bytes()
    document = parse_article_html(payload, canonical_url=ARTICLE_URL, expected_qid="Q163872")

    with Session(engine) as db:
        db.add(LanguageEdition(
            code="en", display_name="English", native_name="English", script="Latin",
            enabled=True, status="live",
        ))
        collection = ReferenceCollection(
            code="article-citation-fixture", title="Article citation fixture",
            description="Isolated passage-to-chunk provenance test", language_code="en",
            selection_method="test_fixture", selection_version="1",
        )
        db.add(collection)
        db.flush()
        source = source_for_wikipedia(db)
        policy = wikipedia_article_html_policy(db, source, robots_sha256=hashlib.sha256(b"retained-test-policy").hexdigest())
        run = RawIngestionRun(
            source_id=source.id,
            access_policy_id=policy.id,
            adapter_name="wikipedia_article_html_snapshot",
            adapter_version=ADAPTER_VERSION,
            status="running",
            records_requested=1,
        )
        db.add(run)
        db.flush()

        snapshot, created, assertion_count = persist_article_snapshot(
            db, source=source, run=run, payload=payload, document=document,
            media_type="text/html", storage_root=tmp_path,
        )
        db.commit()
        snapshot_id = snapshot.id

        assert created is True
        assert snapshot.source_revision == "1383150687"
        assert snapshot.canonical_url == ARTICLE_URL
        assert snapshot.license == "CC BY-SA 4.0"
        assert snapshot.attribution_url == ARTICLE_URL
        assert snapshot.content_hash == hashlib.sha256(payload).hexdigest()
        assert Path(urlparse(snapshot.storage_uri).path).read_bytes() == payload
        assert assertion_count == 5
        assert policy.decision == "allowed"
        assert policy.allowed_paths == ["https://en.wikipedia.org/wiki/*"]
        assert policy.max_concurrency == 1
        assert db.scalar(select(SourceAssertion).where(
            SourceAssertion.source_snapshot_id == snapshot.id,
            SourceAssertion.source_property == "wikidata_item",
        )).raw_value == {"wikidata_id": "Q163872"}

        first = extract_passages(db, "Q163872")
        second = extract_passages(db, "Q163872")
        passages = list(db.scalars(select(NarrativePassage).where(
            NarrativePassage.source_snapshot_id == snapshot_id,
            NarrativePassage.extraction_version == ARTICLE_HTML_EXTRACTION_VERSION,
        ).order_by(NarrativePassage.section_locator)))

        assert first["passages_created"] == 3
        assert second["passages_created"] == 0
        assert {passage.section_locator for passage in passages} == {
            "lead", "plot", "production/development",
        }
        assert next(passage for passage in passages if passage.section_locator == "plot").citation_markers == ["cite_ref-1"]
        assert all(passage.source_snapshot_id == snapshot_id for passage in passages)
        plot = next(passage for passage in passages if passage.section_locator == "plot")
        assert plot.extraction_version == ARTICLE_HTML_EXTRACTION_VERSION
        assert plot.citation_positions == [{
            "marker_id": "cite_ref-1", "paragraph_index": 0,
            "char_offset": len(plot.content),
        }]
        current = current_passage_rows(db, {plot.subject_entity_id})
        assert {passage.extraction_version for passage, _ in current} == {
            ARTICLE_HTML_EXTRACTION_VERSION,
        }
        assert has_plot(db, plot.subject_entity_id) is True
        db.add(ReferenceCollectionMembership(
            collection_code=collection.code, entity_id=plot.subject_entity_id,
            source_reference=ARTICLE_URL,
        ))
        db.commit()
        build_evidence_chunks(
            db, collection_code=collection.code,
            config=ChunkConfiguration(
                source_parser_version=ADAPTER_VERSION,
                extraction_version=ARTICLE_HTML_EXTRACTION_VERSION,
                minimum_words=1,
            ),
        )
        persisted_chunks = list(db.scalars(select(EvidenceChunk).where(
            EvidenceChunk.narrative_passage_id == plot.id,
        )))
        assert len(persisted_chunks) == 1
        assert persisted_chunks[0].citation_positions == plot.citation_positions
        quality = evidence_chunk_quality_report(
            db, collection_code=collection.code,
            config=ChunkConfiguration(
                source_parser_version=ADAPTER_VERSION,
                extraction_version=ARTICLE_HTML_EXTRACTION_VERSION,
                minimum_words=1,
            ),
        )
        assert quality["chunks_with_citation_positions"] >= 1
        assert quality["citation_positions_persisted"] >= 1
        assert db.scalar(select(DataSource).where(DataSource.id == source.id)).name == "English Wikipedia"
        assert db.scalar(select(SourceAccessPolicy).where(SourceAccessPolicy.id == policy.id)).robots_decision == "allow_article_path"
