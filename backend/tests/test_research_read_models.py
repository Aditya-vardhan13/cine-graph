"""Real PostgreSQL regression checks using a small retained source excerpt."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Assertion, CanonicalEntity, DataSource, EmbeddingIndexRun, EmbeddingModel,
    EvidenceChunk, EvidenceChunkRun, EvidenceEmbedding, LanguageEdition,
    NarrativePassage, ReferenceCollection, ReferenceCollectionMembership, SourceObject, SourceSnapshot,
    ResearchAnswer, ResearchAnswerEvidence,
)
from app.schemas import CorpusQualityOut, ResearchFilmOut
from app.services.corpus_quality import corpus_quality_report
from app.services.evidence_coverage import passage_coverage_report
from app.services.evidence_preprocessing import ChunkConfiguration, build_evidence_chunks
from app.services.embedding_artifacts import document_cache_key, embedding_configuration_hash
from app.services.embedding_index import _ordered_chunks_and_contents, instruction_hash
from app.services.embedding_index_reuse import create_exact_reuse_index, plan_exact_embedding_reuse
from app.services.embedding_evaluation import _evaluation_rows
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


def test_recovered_chunk_run_reuses_vectors_only_for_exact_indexed_documents(research_db):
    source_result = build_evidence_chunks(research_db, collection_code=COLLECTION)
    source_run = research_db.get(EvidenceChunkRun, source_result["run_id"])
    source_chunks = list(research_db.scalars(select(EvidenceChunk).where(
        EvidenceChunk.preprocessing_run_id == source_run.id,
        EvidenceChunk.quality_status == "eligible",
    )))
    assert source_chunks
    first_chunk = source_chunks[0]
    second_content = first_chunk.content + " A second distinct passage supports a separate retrieval input."
    second_chunk = EvidenceChunk(
        preprocessing_run_id=source_run.id,
        narrative_passage_id=first_chunk.narrative_passage_id,
        subject_entity_id=first_chunk.subject_entity_id,
        source_snapshot_id=first_chunk.source_snapshot_id,
        language_code=first_chunk.language_code,
        section_locator=first_chunk.section_locator,
        section_title=first_chunk.section_title,
        chunk_ordinal=first_chunk.chunk_ordinal + 1,
        content=second_content,
        content_hash=hashlib.sha256(second_content.encode("utf-8")).hexdigest(),
        word_count=first_chunk.word_count + 9,
        token_count_estimate=first_chunk.token_count_estimate + 10,
        sentence_count=first_chunk.sentence_count + 1,
        quality_status="eligible",
        quality_flags=[],
        duplicate_of_chunk_id=None,
        chunker_version=first_chunk.chunker_version,
        configuration_hash=first_chunk.configuration_hash,
    )
    research_db.add(second_chunk)
    research_db.flush()
    source_chunks.append(second_chunk)

    target_hash = hashlib.sha256(b"recovered-source-run").hexdigest()
    target_run = EvidenceChunkRun(
        collection_code=COLLECTION,
        language_code=source_run.language_code,
        chunker_version=source_run.chunker_version,
        configuration=dict(source_run.configuration),
        configuration_hash=target_hash,
        status="complete",
        passages_requested=source_run.passages_requested,
        passages_eligible=source_run.passages_eligible,
        chunks_created=len(source_chunks),
        completed_at=datetime.now(timezone.utc),
    )
    research_db.add(target_run)
    research_db.flush()
    target_chunks = []
    for source_chunk in source_chunks:
        target_chunk = EvidenceChunk(
            preprocessing_run_id=target_run.id,
            narrative_passage_id=source_chunk.narrative_passage_id,
            subject_entity_id=source_chunk.subject_entity_id,
            source_snapshot_id=source_chunk.source_snapshot_id,
            language_code=source_chunk.language_code,
            section_locator=source_chunk.section_locator,
            section_title=source_chunk.section_title,
            chunk_ordinal=source_chunk.chunk_ordinal,
            content=source_chunk.content,
            content_hash=source_chunk.content_hash,
            word_count=source_chunk.word_count,
            token_count_estimate=source_chunk.token_count_estimate,
            sentence_count=source_chunk.sentence_count,
            quality_status=source_chunk.quality_status,
            quality_flags=list(source_chunk.quality_flags),
            duplicate_of_chunk_id=None,
            chunker_version=source_chunk.chunker_version,
            configuration_hash=target_hash,
        )
        target_chunks.append(target_chunk)
    research_db.add_all(target_chunks)
    research_db.flush()

    instruction = "Retrieve exact source-backed film evidence."
    revision = f"integration-{uuid4().hex}"
    model = EmbeddingModel(
        provider="ollama", model_name="qwen3-embedding:0.6b", model_revision=revision,
        dimension=1024, query_instruction=instruction, instruction_hash=instruction_hash(instruction),
        license="Apache-2.0",
    )
    research_db.add(model)
    research_db.flush()
    config_hash = embedding_configuration_hash(
        model_name=model.model_name, model_revision=model.model_revision,
        dimension=model.dimension, instruction_hash=model.instruction_hash,
    )
    source_index = EmbeddingIndexRun(
        evidence_chunk_run_id=source_run.id,
        embedding_model_id=model.id,
        document_representation="film-section-evidence-v1",
        configuration={},
        configuration_hash=config_hash,
        status="complete",
        chunks_requested=len(source_chunks),
        chunks_completed=len(source_chunks),
        completed_at=datetime.now(timezone.utc),
    )
    research_db.add(source_index)
    research_db.flush()
    _, source_contents = _ordered_chunks_and_contents(research_db, source_run)
    cache_key = document_cache_key(
        provider=model.provider, model_name=model.model_name, dimensions=model.dimension,
        chunk_run_id=str(source_run.id), chunker_version=source_run.chunker_version,
        contents=source_contents,
    )
    source_index.configuration = {"cache_key": cache_key}
    expected_vectors = {}
    for ordinal, source_chunk in enumerate(source_chunks):
        vector = [float(ordinal + 1)] + [0.0] * 1023
        expected_vectors[source_chunk.id] = vector
        research_db.add(EvidenceEmbedding(
            index_run_id=source_index.id,
            evidence_chunk_id=source_chunk.id,
            content_hash=source_chunk.content_hash,
            embedding=vector,
        ))
    research_db.commit()

    plan = plan_exact_embedding_reuse(
        research_db, source_index_id=source_index.id, target_chunk_run_id=target_run.id,
    )
    assert plan["source_cache_key_verified"] is True
    assert plan["exact_document_pairs"] == len(target_chunks)

    target_index = create_exact_reuse_index(
        research_db, source_index_id=source_index.id, target_chunk_run_id=target_run.id,
    )
    copied = dict(research_db.execute(
        select(EvidenceEmbedding.evidence_chunk_id, EvidenceEmbedding.embedding).where(
            EvidenceEmbedding.index_run_id == target_index.id,
        )
    ).all())
    expected_by_content = {chunk.content_hash: expected_vectors[chunk.id] for chunk in source_chunks}
    assert target_index.status == "complete"
    assert target_index.chunks_completed == len(target_chunks)
    assert all(
        list(copied[chunk.id]) == expected_by_content[chunk.content_hash]
        for chunk in target_chunks
    )

    target_chunks[0].content = "Changed text must never inherit a vector."
    with pytest.raises(ValueError, match="Exact vector reuse rejected"):
        plan_exact_embedding_reuse(
            research_db, source_index_id=source_index.id, target_chunk_run_id=target_run.id,
        )
    research_db.rollback()


def test_retrieval_evaluation_maps_reviewed_passages_across_exact_source_recovery(research_db):
    result = build_evidence_chunks(research_db, collection_code=COLLECTION)
    run = research_db.get(EvidenceChunkRun, result["run_id"])
    current_chunks = list(research_db.scalars(select(EvidenceChunk).where(
        EvidenceChunk.preprocessing_run_id == run.id,
        EvidenceChunk.quality_status == "eligible",
    )))
    assert current_chunks
    current_passage = research_db.get(NarrativePassage, current_chunks[0].narrative_passage_id)
    current_snapshot = research_db.get(SourceSnapshot, current_passage.source_snapshot_id)
    source_object = research_db.get(SourceObject, current_snapshot.source_object_id)

    old_snapshot = SourceSnapshot(
        source_object_id=source_object.id,
        source_revision=current_snapshot.source_revision,
        canonical_url=current_snapshot.canonical_url,
        content_hash=hashlib.sha256(b"recovered full-page payload").hexdigest(),
        license=current_snapshot.license,
        fetch_status="success",
        parser_version="recovered-test-v2",
    )
    research_db.add(old_snapshot)
    research_db.flush()
    old_passage = NarrativePassage(
        subject_entity_id=current_passage.subject_entity_id,
        source_snapshot_id=old_snapshot.id,
        section_locator=current_passage.section_locator,
        section_title=current_passage.section_title,
        ordinal=current_passage.ordinal,
        language_code=current_passage.language_code,
        content=current_passage.content,
        content_hash=current_passage.content_hash,
        citation_markers=list(current_passage.citation_markers),
        extraction_version="recovered-test-v2",
    )
    answer = ResearchAnswer(
        subject_entity_id=current_passage.subject_entity_id,
        question_id="story.plot_character_structure",
        question_text="What story conflict is shown in this passage?",
        answer="A source-linked answer for integration coverage.",
        evidence_class="narrative_extraction",
        answer_version="test-v1",
        review_status="published",
    )
    research_db.add_all([old_passage, answer])
    research_db.flush()
    research_db.add(ResearchAnswerEvidence(
        research_answer_id=answer.id,
        narrative_passage_id=old_passage.id,
        evidence_locator="plot",
    ))
    research_db.flush()

    eligible_chunks, queries = _evaluation_rows(research_db, run)
    query = next(item for item in queries if item["research_answer_id"] == str(answer.id))
    expected_ids = {str(chunk.id) for chunk in eligible_chunks if chunk.narrative_passage_id == current_passage.id}
    assert expected_ids
    assert query["target_chunk_ids"] == expected_ids


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
