"""Explicit, isolated retrieval canary over four real refreshed articles."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import router
from app.core.config import get_settings
from app.db import Base, get_db
from app.models import (CanonicalEntity, DataSource, Film, LanguageEdition, NarrativePassage,
                        NarrativeUseDecision, ReferenceCollection, ReferenceCollectionMembership,
                        SourceObject, SourceSnapshot)
from app.services.ollama_embeddings import OllamaEmbeddingClient
from app.services.story_comparison import compare_story_evidence
from app.services.wikipedia_article_html import parse_article_html
from app.services.wikipedia_raw import ADAPTER_VERSION
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_refreshed_articles_retrieve_against_user_questions(tmp_path):
    if os.environ.get("CINEGRAPH_REFRESHED_SOURCE_CANARY") != "1":
        pytest.skip("explicit retained-source and local Ollama canary only")
    from app.services.writer_catalog_index import index_writer_catalog
    directory = Path("data/evaluation/writer-source-audit/wikipedia-refresh-v1").resolve()
    captures = json.loads((directory / "checkpoint.json").read_bytes())["captures"]
    films = [("Avengers: Endgame", "Q23781155"), ("The Godfather", "Q47703"),
             ("Her", "Q788822"), ("WALL-E", "Q104905")]
    ollama = os.environ.get("CINEGRAPH_TEST_OLLAMA_URL", "http://host.docker.internal:11434")
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    collection = get_settings().writer_catalog_collection_code
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin", enabled=True, status="active"))
        db.add(ReferenceCollection(code=collection, title="Refreshed source canary", description="Isolated research only",
                                   language_code="en", selection_method="fixture", selection_version="v1"))
        source = DataSource(name="English Wikipedia", url="https://en.wikipedia.org/", source_type="wiki",
                            license="CC BY-SA 4.0", rights_status="attributed_reuse")
        db.add(source)
        db.flush()
        entities = {}
        for title, qid in films:
            capture = captures[qid]
            assert capture["status"] == "review_candidate" and capture.get("storage_encoding", "identity") == "identity"
            path = directory / "snapshots" / f"{capture['sha256']}.html"
            payload = path.read_bytes()
            assert hashlib.sha256(payload).hexdigest() == capture["sha256"]
            doc = parse_article_html(payload, canonical_url=capture["canonical_url"], expected_qid=qid)
            assert doc.metadata.title == capture["metadata"]["title"] and doc.metadata.page_id == capture["metadata"]["page_id"]
            entity = CanonicalEntity(canonical_label=title, entity_kind="film", wikidata_id=qid)
            db.add(entity)
            db.flush()
            entities[qid] = entity.id
            db.add(Film(entity_id=entity.id, canonical_title=title, original_language_code="en", wikidata_id=qid))
            db.add(ReferenceCollectionMembership(collection_code=collection, entity_id=entity.id,
                                                  source_reference="isolated-refreshed-canary", status="included"))
            obj = SourceObject(source_id=source.id, external_id=f"enwiki:{doc.metadata.page_id}",
                               object_kind="wiki_page", canonical_url=doc.metadata.canonical_url)
            db.add(obj)
            db.flush()
            snapshot = SourceSnapshot(source_object_id=obj.id, source_revision=str(doc.metadata.revision_id),
                                      canonical_url=doc.metadata.canonical_url, attribution_url=doc.metadata.canonical_url,
                                      content_hash=capture["sha256"], byte_size=len(payload), storage_uri=path.as_uri(),
                                      parser_version=ADAPTER_VERSION, license="CC BY-SA 4.0", fetch_status="success")
            db.add(snapshot)
            db.flush()
            db.add(NarrativeUseDecision(source_snapshot_id=snapshot.id, use_case="semantic_index_and_model_input",
                                        decision="approved", decision_version=1, reviewer="isolated-test-only",
                                        decision_notes="Isolated local research, not product approval.",
                                        decision_basis_url="https://creativecommons.org/licenses/by-sa/4.0/"))
            plot = [passage for passage in doc.passages if passage.section_locator.split("/", 1)[0] in {"plot", "synopsis"}]
            assert plot
            for passage in plot:
                db.add(NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=snapshot.id,
                                        section_locator=passage.section_locator, section_title=passage.section_title,
                                        ordinal=passage.ordinal, language_code="en", content=passage.content,
                                        content_hash=passage.content_hash, citation_markers=list(passage.citation_markers),
                                        extraction_version=doc.parser_version))
        db.commit()
        report = index_writer_catalog(db, collection_code=collection, cache_dir=tmp_path / "vectors", ollama_url=ollama, batch_size=4)
        assert report["status"] == "complete" and report["films"] == 4
        questions = [("Q23781155", "Q47703", "how do these follow the conflicts between family or close people when fighting injustice"),
                     ("Q788822", "Q104905", "How does each film make an artificial companion expose human loneliness?")]
        for first, second, question in questions:
            result = compare_story_evidence(db, first_entity_id=entities[first], second_entity_id=entities[second],
                                            question=question, collection_code=collection,
                                            embedding_client=OllamaEmbeddingClient(base_url=ollama))
            print("REFRESHED_CANARY", first, second, result.retrieval_method, result.answerability_status)
            for lens in result.lenses:
                print("LENS", lens.label, (lens.first_evidence.excerpt if lens.first_evidence else None),
                      (lens.second_evidence.excerpt if lens.second_evidence else None))
                for index, option in enumerate(lens.second_options, 1):
                    print("SECOND_OPTION", second, index, option.excerpt)
            assert result.retrieval_method == "hybrid"
        app = FastAPI()
        app.include_router(router)

        def isolated_session():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db] = isolated_session
        with TestClient(app) as client:
            response = client.post("/api/v1/comparisons/story", json={
                "first_entity_id": str(entities["Q23781155"]), "second_entity_id": str(entities["Q47703"]),
                "question": questions[0][2], "retrieval_method": "hybrid",
            })
        assert response.status_code == 200
        assert response.json()["retrieval_method"] == "hybrid"
    engine.dispose()
