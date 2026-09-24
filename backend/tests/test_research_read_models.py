"""Real PostgreSQL regression checks using a small retained source excerpt."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Assertion, CanonicalEntity, DataSource, EmbeddingIndexRun, EmbeddingModel,
    EvidenceChunk, EvidenceChunkRun, EvidenceEmbedding, LanguageEdition,
    NarrativePassage, ReferenceCollection, ReferenceCollectionMembership, SourceObject, SourceSnapshot,
)
from app.schemas import CorpusQualityOut, ResearchFilmOut
from app.services.corpus_quality import corpus_quality_report
from app.services.evidence_coverage import passage_coverage_report
from app.services.evidence_preprocessing import ChunkConfiguration, build_evidence_chunks
from app.services.hybrid_evidence_retrieval import NarrativeRetrievalMethod, retrieve_narrative_candidates
from app.services.research_catalog import search_research_films
from app.services.retrieval_scope import resolve_retrieval_scope
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration
COLLECTION = "retained-fixture-v1"


@pytest.fixture
def research_db():
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    retained = json.loads((Path(__file__).parent / "fixtures/her-research-retained-v1.json").read_text())
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin", enabled=True))
        source = DataSource(name="English Wikipedia", url="https://en.wikipedia.org/", source_type="wiki",
                            license="CC BY-SA 4.0", rights_status="open")
        film = CanonicalEntity(canonical_label="Her (2013 film)", entity_kind="film", wikidata_id="Q788822")
        db.add_all([source, film])
        db.flush()
        db.add(ReferenceCollection(code=COLLECTION, title="Retained fixture", description="Offline test",
                                   language_code="en", selection_method="fixture", selection_version="1"))
        db.flush()
        db.add(ReferenceCollectionMembership(collection_code=COLLECTION, entity_id=film.id,
                                             selection_position=1, selection_signals={},
                                             source_reference=retained["metadata_source"]))
        passage = retained["passage"]
        source_object = SourceObject(source_id=source.id, external_id="Her_(2013_film)", object_kind="article",
                                     canonical_url=passage["source_url"])
        db.add(source_object)
        db.flush()
        digest = hashlib.sha256(passage["content"].encode()).hexdigest()
        snapshot = SourceSnapshot(source_object_id=source_object.id, source_revision=passage["source_revision"],
                                  canonical_url=passage["source_url"], attribution_url=passage["source_url"],
                                  content_hash=digest, license=passage["license"], fetch_status="success",
                                  parser_version="retained-fixture-v1")
        db.add(snapshot)
        db.flush()
        db.add(NarrativePassage(subject_entity_id=film.id, source_snapshot_id=snapshot.id,
                                section_locator="plot", section_title="Plot", ordinal=0,
                                content=passage["content"], content_hash=digest,
                                citation_markers=[], extraction_version="retained-test-v1"))
        for assertion in retained["assertions"]:
            db.add(Assertion(subject_entity_id=film.id, predicate=assertion["predicate"],
                             value_json=assertion["value"], qualifiers={}, assertion_kind="source_fact",
                             review_status="resolved", rank="normal", source_reference=retained["metadata_source"],
                             source_revision=retained["metadata_revision"]))
        db.commit()
        yield db
    engine.dispose()


def test_canonical_metadata_works_without_legacy_profile(research_db):
    films = search_research_films(research_db, query_text="her", collection_code=COLLECTION)
    result = ResearchFilmOut(**films[0].__dict__)
    assert result.film_id is None
    assert result.title == "Her"
    assert str(result.release_date) == "2013-10-12"
    assert result.release_year == 2013
    assert result.runtime_minutes == 126
    assert result.language_code == "en"
    assert result.genre_ids == ["Q471839"]
    assert result.metadata_evidence["release_event"][0]["source_revision"] == "2513891788"


def test_coverage_counts_passages_without_legacy_documents(research_db):
    result = CorpusQualityOut(**corpus_quality_report(research_db, collection_code=COLLECTION))
    assert result.films == 0
    assert result.research.films == result.research.films_with_passages == 1
    assert result.research.narrative_passages == 1
    assert result.research.resolved_assertions == 4
    assert result.research.indexed_chunks == 0
    assert result.sources[0].narrative_documents == 0
    assert result.sources[0].narrative_passages == 1
    assert result.critical_claims == result.pending_critical_candidates == 0


def test_versioned_passage_coverage_reports_films_and_heading_proxy(research_db):
    report = passage_coverage_report(
        research_db, collection_code=COLLECTION,
        source_parser_version="retained-fixture-v1", include_films=True,
    )
    assert report["films"] == report["films_with_passages"] == 1
    assert report["films_with_category"]["plot"] == 1
    assert report["film_rows"][0]["passages"] == 1
    assert passage_coverage_report(
        research_db, collection_code=COLLECTION,
        source_parser_version="other-version",
    )["films_without_passages"] == 1


def test_preprocessing_selects_only_one_source_version(research_db):
    db = research_db
    original = db.scalar(select(SourceSnapshot).where(SourceSnapshot.parser_version == "retained-fixture-v1"))
    old_passage = db.scalar(select(NarrativePassage).where(NarrativePassage.source_snapshot_id == original.id))
    recovered = SourceSnapshot(
        source_object_id=original.source_object_id, source_revision="recovered-fixture-revision",
        canonical_url=original.canonical_url, attribution_url=original.attribution_url,
        content_hash="b" * 64, license=original.license, fetch_status="success",
        parser_version="retained-recovery-fixture-v1",
    )
    db.add(recovered)
    db.flush()
    db.add(NarrativePassage(
        subject_entity_id=old_passage.subject_entity_id, source_snapshot_id=recovered.id,
        section_locator="plot", section_title="Plot", ordinal=0,
        content=old_passage.content, content_hash=old_passage.content_hash,
        citation_markers=[], extraction_version="retained-recovery-fixture-v1",
    ))
    db.commit()

    with pytest.raises(ValueError, match="multiple source parser versions"):
        build_evidence_chunks(db, collection_code=COLLECTION)
    result = build_evidence_chunks(
        db, collection_code=COLLECTION,
        config=ChunkConfiguration(source_parser_version="retained-recovery-fixture-v1"),
    )
    assert result["passages_requested"] == 1
    assert result["passages_eligible"] == 1
    chunks = list(db.scalars(select(EvidenceChunk)))
    assert chunks
    assert all(chunk.source_snapshot_id == recovered.id for chunk in chunks)


def test_lexical_and_dense_rank_the_same_pinned_run_despite_newer_versions(research_db):
    db = research_db
    build_evidence_chunks(db, collection_code=COLLECTION)
    indexed_chunk_run = db.scalar(select(EvidenceChunkRun))
    old_chunks = db.scalars(select(EvidenceChunk).where(
        EvidenceChunk.preprocessing_run_id == indexed_chunk_run.id, EvidenceChunk.quality_status == "eligible",
    )).all()
    # These unit vectors test persisted cosine/rank SQL, not model quality.
    model = EmbeddingModel(provider="ollama", model_name="fixture-vector", model_revision="test-math-v1",
                           dimension=1024, query_instruction="fixture", instruction_hash="a" * 64, license="test")
    db.add(model)
    db.flush()
    index = EmbeddingIndexRun(evidence_chunk_run_id=indexed_chunk_run.id, embedding_model_id=model.id,
                              document_representation="test", configuration={}, configuration_hash="a" * 64,
                              status="complete", chunks_requested=len(old_chunks), chunks_completed=len(old_chunks),
                              completed_at=datetime.now(timezone.utc))
    db.add(index)
    db.flush()
    vector = [1.0] + [0.0] * 1023
    for chunk in old_chunks:
        db.add(EvidenceEmbedding(index_run_id=index.id, evidence_chunk_id=chunk.id,
                                 content_hash=chunk.content_hash, embedding=vector))
    db.commit()
    build_evidence_chunks(db, collection_code=COLLECTION, config=ChunkConfiguration(target_tokens=100, maximum_tokens=150))
    scope = resolve_retrieval_scope(db, collection_code=COLLECTION, model_name=model.model_name)
    assert scope.preprocessing_run_id == indexed_chunk_run.id
    kwargs = dict(subject_entity_id=old_chunks[0].subject_entity_id,
                  question_id="story.writer_focus", question_text="Theodore Samantha relationship",
                  scope=scope, limit=10)
    lexical = retrieve_narrative_candidates(db, method=NarrativeRetrievalMethod.LEXICAL, **kwargs)
    hybrid = retrieve_narrative_candidates(db, method=NarrativeRetrievalMethod.HYBRID, query_vector=vector, **kwargs)
    expected = {str(c.id) for c in old_chunks}
    assert {e.chunk_id for e in lexical.evidence} == expected
    assert {e.chunk_id for e in hybrid.evidence} == expected
    assert all(e.matched_by == ("semantic", "lexical") for e in hybrid.evidence)
    assert lexical.preprocessing_run_id == hybrid.preprocessing_run_id == str(indexed_chunk_run.id)

    # A newer index from another collection cannot replace this selection.
    db.add(ReferenceCollection(code="unrelated", title="Other", description="Other", language_code="en",
                              selection_method="test", selection_version="1"))
    db.flush()
    other_run = EvidenceChunkRun(collection_code="unrelated", language_code="en", chunker_version="other",
                                configuration={}, configuration_hash="b" * 64, status="complete")
    db.add(other_run)
    db.flush()
    db.add(EmbeddingIndexRun(evidence_chunk_run_id=other_run.id, embedding_model_id=model.id,
                            document_representation="test", configuration={}, configuration_hash="b" * 64,
                            status="complete", chunks_requested=0, chunks_completed=0,
                            completed_at=datetime.now(timezone.utc) + timedelta(days=1)))
    db.commit()
    assert resolve_retrieval_scope(db, collection_code=COLLECTION, model_name=model.model_name).index_run.id == index.id
    with pytest.raises(ValueError, match="No completed narrative"):
        resolve_retrieval_scope(db, collection_code="missing")
