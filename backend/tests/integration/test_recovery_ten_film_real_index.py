"""Explicit, local-only replay of ten retained film sources into a test schema."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import Base
from app.models import (CanonicalEntity, DataSource, LanguageEdition, NarrativePassage,
    NarrativeUseDecision, ReferenceCollection, ReferenceCollectionMembership, SourceObject, SourceSnapshot)
from app.services.corpus_build_manifest import canonical_digest
from app.services.embedding_index_audit import audit_index
from app.services.hybrid_evidence_retrieval import NarrativeRetrievalMethod, retrieve_narrative_candidates
from app.services.ollama_embeddings import OllamaEmbeddingClient
from app.services.retrieval_scope import resolve_retrieval_scope
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.writer_catalog_index import index_writer_catalog, recovery_profile
from tests.postgres_test_db import isolated_postgres_engine
from tests.vector_canary_manifest import save_canary_vector_manifest


pytestmark = pytest.mark.integration


def test_ten_retained_films_into_pinned_4b_index():
    if os.environ.get("CINEGRAPH_TEN_FILM_CANARY") != "1":
        pytest.skip("explicit local real-source 4B canary only")
    root = Path("data/evaluation")
    corpus = json.loads((root / "recovery-ten-film-current-v1.json").read_text())
    descriptors = json.loads((root / "recovery-ten-film-descriptors-v1.json").read_text())
    for obj in (corpus, descriptors):
        assert canonical_digest({k:v for k,v in obj.items() if k != "fingerprint"}) == obj["fingerprint"]
    assert descriptors["corpus_fingerprint"] == corpus["fingerprint"]
    output = root / "recovery-ten-film-pgvector-4b-canary-v2.json"
    cache_dir = root / "recovery-ten-film-vector-cache-v2"
    mapping_path = root / "recovery-ten-film-vector-mapping-v2.json"
    if output.exists() or mapping_path.exists():
        raise FileExistsError("Canary output or vector mapping already exists")
    docs = corpus["documents"]
    sources = {s["snapshot_id"]:s for s in descriptors["sources"]}
    assert len(docs) == 487 and len(sources) == 10
    films = {d["film_qid"]:(d["entity_id"],d["film_title"]) for d in docs}
    assert len(films) == 10 and {d["source_snapshot_id"] for d in docs} == set(sources)
    for source in sources.values():
        assert verify_snapshot_file(source["storage_uri"],source["content_hash"],source["byte_size"]) == "verified"
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    code = get_settings().writer_catalog_collection_code
    model = recovery_profile("qwen3-embedding:4b", "df5bd2e3c74cd8d069d21dc038f1b359fcdc9458fce1c99bd43c9eb1518ff907")
    ollama_url = os.environ.get("CINEGRAPH_TEST_OLLAMA_URL", "http://127.0.0.1:11434")
    with Session(engine) as db:
        db.add(LanguageEdition(code="en",display_name="English",script="Latin",enabled=True,status="active"))
        db.add(ReferenceCollection(code=code,title="Local ten-film canary",description="Isolated evaluation only",
            language_code="en",selection_method="retained pilot replay",selection_version="v1"))
        source = DataSource(name="English Wikipedia",url="https://en.wikipedia.org/",source_type="wiki",
            license="CC BY-SA 4.0",rights_status="attributed_reuse")
        db.add(source); db.flush()
        for qid,(entity_id,title) in films.items():
            eid=UUID(entity_id)
            db.add(CanonicalEntity(id=eid,canonical_label=title,entity_kind="film",wikidata_id=qid))
            db.flush()
            db.add(ReferenceCollectionMembership(collection_code=code,entity_id=eid,
                source_reference="frozen_pilot:"+corpus["fingerprint"],status="included"))
        for s in sources.values():
            oid,sid=UUID(s["object_id"]),UUID(s["snapshot_id"])
            db.add(SourceObject(id=oid,source_id=source.id,external_id=s["external_id"],
                object_kind=s["object_kind"],canonical_url=s["canonical_url"]))
            db.flush()
            db.add(SourceSnapshot(id=sid,source_object_id=oid,source_revision=s["source_revision"],
                canonical_url=s["canonical_url"],retrieved_at=datetime.fromisoformat(s["retrieved_at"]),
                content_hash=s["content_hash"],byte_size=s["byte_size"],storage_uri=s["storage_uri"],
                license=s["license"],attribution_url=s["attribution_url"],parser_version=s["parser_version"],fetch_status="success"))
            db.flush()
            db.add(NarrativeUseDecision(source_snapshot_id=sid,use_case="semantic_index_and_model_input",
                decision="approved",decision_version=s["decision_version"],decision_basis_url=s["decision_basis_url"],
                decision_notes=s["decision_notes"],reviewer=s["reviewer"]))
        for d in docs:
            assert hashlib.sha256(d["content"].encode()).hexdigest() == d["content_sha256"]
            s=sources[d["source_snapshot_id"]]
            assert (d["source_sha256"],d["source_revision"],d["decision_version"]) == (
                s["content_hash"],s["source_revision"],s["decision_version"])
            db.add(NarrativePassage(id=UUID(d["chunk_id"]),subject_entity_id=UUID(d["entity_id"]),
                source_snapshot_id=UUID(d["source_snapshot_id"]),section_locator=d["section_locator"],
                section_title=d["section_title"],ordinal=d["passage_ordinal"],language_code="en",
                content=d["content"],content_hash=d["content_sha256"],citation_markers=[],
                extraction_version=d["extraction_version"]))
        db.commit()
        build=index_writer_catalog(db,collection_code=code,cache_dir=cache_dir,ollama_url=ollama_url,
            batch_size=4,profile=model)
        assert build["status"] == "complete" and build["films"] == 10
        audit=audit_index(db,UUID(build["index_run_id"]))
        assert audit["integrity_pass"]
        mapping = save_canary_vector_manifest(db, run_id=build["chunk_report"]["run_id"],
            profile=model, model_digest=build["model_digest"], cache_dir=cache_dir,
            output=mapping_path, corpus_fingerprint=corpus["fingerprint"])
        scope=resolve_retrieval_scope(db,collection_code=code,index_run_id=UUID(build["index_run_id"]))
        client=OllamaEmbeddingClient(base_url=ollama_url)
        probes=[{"case_id":"user-endgame-godfather", "film_qids":["Q23781155","Q47703"],
                 "question":"how do these follow the conflicts between family or close people when fighting injustice"},
                *corpus["cases"]]
        results=[]
        for probe in probes:
            question = probe["question"]
            # One embedding per question, shared across the two scoped film searches.
            query_vector = client.embed([model.query_input(question)], profile=model)[0]
            sides=[]
            for qid in probe["film_qids"]:
                methods = {}
                for method in (NarrativeRetrievalMethod.SEMANTIC, NarrativeRetrievalMethod.LEXICAL):
                    response=retrieve_narrative_candidates(db,subject_entity_id=UUID(films[qid][0]),
                        question_id="story.plot_character_structure",question_text=question,
                        method=method,scope=scope,client=client,
                        query_vector=query_vector if method == NarrativeRetrievalMethod.SEMANTIC else None,
                        restrict_sections=False,limit=20)
                    methods[method.value] = asdict(response)
                sides.append({"film_qid":qid,"methods":methods})
            results.append({"case_id":probe["case_id"],"question":question,"sides":sides})
            print(f"Completed {probe['case_id']} ({len(results)}/{len(probes)})", flush=True)
        report={"corpus_fingerprint":corpus["fingerprint"],"descriptor_fingerprint":descriptors["fingerprint"],
            "build":build,"audit":audit,"probes":results,"quality_review":"pending",
            "vector_mapping":str(mapping_path),"vector_mapping_fingerprint":mapping["fingerprint"],
            "caution":"Isolated test-schema canary; not a serving index or an answer-quality score."}
        with output.open("x") as handle:
            json.dump(report,handle,ensure_ascii=False,indent=2); handle.write("\n")
    engine.dispose()
