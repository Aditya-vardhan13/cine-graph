"""Explicit local integration test: PostgreSQL/pgvector and real Ollama."""
import hashlib
import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.config import get_settings
from app.db import Base
from app.models import (CanonicalEntity, DataSource, LanguageEdition, NarrativePassage,
                        NarrativeUseDecision, ReferenceCollection, ReferenceCollectionMembership,
                        SourceObject, SourceSnapshot)
from app.services.hybrid_evidence_retrieval import NarrativeRetrievalMethod, retrieve_narrative_candidates
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.retrieval_scope import resolve_retrieval_scope
from app.services.writer_catalog_index import index_writer_catalog
from app.services.embedding_index import _candidate_run, import_embedding_cache
from app.services.evidence_preprocessing import CHUNKER_VERSION, ChunkConfiguration, build_evidence_chunks
from app.services.ollama_embeddings import MANIFEST_REVISION_PREFIX
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_reviewed_writer_index_builds_and_retrieves_with_real_ollama(tmp_path):
    if os.environ.get("CINEGRAPH_LIVE_OLLAMA_TEST") != "1":
        pytest.skip("explicit local Ollama contract check only")
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    code = get_settings().writer_catalog_collection_code
    ollama_url = os.environ.get("CINEGRAPH_TEST_OLLAMA_URL", "http://127.0.0.1:11434")
    subject_ids = []
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin", enabled=True, status="active"))
        db.add(ReferenceCollection(code=code, title="Writer test", description="Isolated fixture",
                                   language_code="en", selection_method="fixture", selection_version="v1"))
        source = DataSource(name="Local retained source", url="https://en.wikipedia.org/",
                            source_type="wiki", license="CC BY-SA 4.0", rights_status="attributed_reuse")
        db.add(source)
        db.flush()
        for number in range(2):
            entity = CanonicalEntity(canonical_label=f"Fixture Film {number}", entity_kind="film")
            db.add(entity)
            db.flush()
            subject_ids.append(entity.id)
            db.add(ReferenceCollectionMembership(collection_code=code, entity_id=entity.id,
                                                  source_reference="isolated-fixture", status="included"))
            url = f"https://en.wikipedia.org/wiki/Fixture_Film_{number}"
            obj = SourceObject(source_id=source.id, external_id=f"fixture-{number}", object_kind="article", canonical_url=url)
            db.add(obj)
            db.flush()
            payload = f"Retained source bytes {number}".encode()
            path = tmp_path / f"source-{number}.html"
            path.write_bytes(payload)
            snap = SourceSnapshot(source_object_id=obj.id, source_revision="fixture-revision",
                                  canonical_url=url, attribution_url=url, parser_version=f"fixture-parser-{number}",
                                  content_hash=hashlib.sha256(payload).hexdigest(), byte_size=len(payload),
                                  storage_uri=path.as_uri(), license="CC BY-SA 4.0", fetch_status="success")
            db.add(snap)
            db.flush()
            db.add(NarrativeUseDecision(source_snapshot_id=snap.id, use_case="semantic_index_and_model_input",
                                        decision="approved", decision_version=1,
                                        decision_basis_url="https://creativecommons.org/licenses/by-sa/4.0/",
                                        decision_notes="Reviewed local integration fixture for model use.", reviewer="test"))
            # Identical text across films must remain retrievable for each film.
            content = ("A family faces a difficult choice when a corrupt official threatens their community. "
                       "The protagonist tries to protect a sibling while challenging the injustice. "
                       "Their plans create consequences for their friends and change their understanding of loyalty. "
                       "They disagree about whether public action or protecting each other should come first. "
                       "After a confrontation the family must decide how much they will risk for justice.")
            db.add(NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=snap.id,
                                    section_locator="plot", section_title="Plot", ordinal=0,
                                    language_code="en", content=content,
                                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                                    citation_markers=[], extraction_version="fixture-v1"))
        db.commit()
        result = index_writer_catalog(db, collection_code=code, cache_dir=tmp_path / "vectors",
                                      ollama_url=ollama_url, batch_size=2)
        assert result["status"] == "complete"
        assert result["films"] == 2 and result["chunks_completed"] == 2
        original_run = UUID(result["chunk_report"]["run_id"])
        alternate = build_evidence_chunks(db, collection_code=code, config=ChunkConfiguration(
            target_tokens=100, maximum_tokens=120, overlap_tokens=20,
            current_extractions_per_snapshot=True,
        ))
        assert UUID(alternate["run_id"]) != original_run
        assert _candidate_run(db, collection_code=code, chunker_version=CHUNKER_VERSION).id == UUID(alternate["run_id"])
        assert _candidate_run(db, collection_code=code, chunker_version=CHUNKER_VERSION, run_id=original_run).id == original_run
        with pytest.raises(ValueError, match="No completed evidence chunk run"):
            _candidate_run(db, collection_code="other-collection", chunker_version=CHUNKER_VERSION, run_id=original_run)
        cache_path = next((tmp_path / "vectors").rglob("*.npy"))
        profile = OllamaEmbeddingProfile()
        import_args = dict(cache_path=cache_path, collection_code=code, chunker_version=CHUNKER_VERSION,
                           model_name=profile.model, model_revision=MANIFEST_REVISION_PREFIX + result["model_digest"],
                           dimension=profile.dimensions, query_instruction=profile.query_instruction)
        with pytest.raises(ValueError, match="Embedding cache identity"):
            import_embedding_cache(db, **import_args)
        assert str(import_embedding_cache(db, chunk_run_id=original_run, **import_args).id) == result["index_run_id"]
        second = index_writer_catalog(db, collection_code=code, cache_dir=tmp_path / "vectors",
                                      ollama_url=ollama_url, batch_size=2)
        assert second["cache_reused"] and second["index_run_id"] == result["index_run_id"]
        scope = resolve_retrieval_scope(db, collection_code=code)
        for entity_id in subject_ids:
            found = retrieve_narrative_candidates(db, subject_entity_id=entity_id,
                        question_id="story.plot_character_structure", question_text="How does family loyalty conflict with justice?",
                        method=NarrativeRetrievalMethod.SEMANTIC, scope=scope, client=OllamaEmbeddingClient(base_url=ollama_url))
            assert found.evidence and found.evidence[0].subject_entity_id == str(entity_id)
        passage = db.scalar(select(NarrativePassage).where(NarrativePassage.subject_entity_id == subject_ids[0]))
        original_content = passage.content
        passage.content = original_content + " Altered after extraction."
        db.flush()
        with pytest.raises(ValueError, match="passage .* failed content integrity"):
            index_writer_catalog(db, collection_code=code, cache_dir=tmp_path / "vectors", ollama_url=ollama_url)
        passage.content = original_content
        db.flush()
        with pytest.raises(ValueError, match="no longer matches"):
            OllamaEmbeddingClient(base_url=ollama_url).embed(["A query"], profile=OllamaEmbeddingProfile(expected_model_digest="0" * 64))
        path.write_bytes(b"tampered test fixture")
        with pytest.raises(ValueError, match="failed integrity"):
            index_writer_catalog(db, collection_code=code, cache_dir=tmp_path / "vectors",
                                 ollama_url=ollama_url)
        path.write_bytes(payload)
        db.add(NarrativeUseDecision(source_snapshot_id=snap.id, use_case="semantic_index_and_model_input",
                                    decision="denied", decision_version=2,
                                    decision_notes="Review revoked for this isolated test.", reviewer="test"))
        db.commit()
        with pytest.raises(ValueError, match="lack an intact approved"):
            index_writer_catalog(db, collection_code=code, cache_dir=tmp_path / "vectors",
                                 ollama_url=ollama_url)
    engine.dispose()
