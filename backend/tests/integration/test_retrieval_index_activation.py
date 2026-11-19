"""Explicit activation never drifts to a newer run or another collection."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.db import Base
from app.models import EmbeddingIndexRun, EmbeddingModel, EvidenceChunkRun, LanguageEdition, ReferenceCollection
from app.services.ollama_embeddings import MANIFEST_REVISION_PREFIX
from app.services.retrieval_scope import resolve_retrieval_scope
from tests.postgres_test_db import isolated_postgres_engine

pytestmark=pytest.mark.integration


def test_explicit_index_pin_is_stable_and_fails_closed():
    engine=isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en",display_name="English",enabled=True,status="active"))
        db.flush()
        db.add(ReferenceCollection(code="pin-test",title="Pin test",description="Isolated fixture",
            language_code="en",selection_method="fixture",selection_version="v1"))
        db.flush()
        chunks=EvidenceChunkRun(collection_code="pin-test",language_code="en",chunker_version="v1",
            configuration={},configuration_hash="a"*64,status="complete")
        model=EmbeddingModel(provider="ollama",model_name="qwen3-embedding:4b",
            model_revision=MANIFEST_REVISION_PREFIX+"b"*64,dimension=1024,
            query_instruction="Retrieve evidence.",instruction_hash="c"*64,license="Apache-2.0")
        db.add_all([chunks,model]); db.flush()
        now=datetime.now(timezone.utc)
        runs=[EmbeddingIndexRun(evidence_chunk_run_id=chunks.id,embedding_model_id=model.id,
            document_representation="fixture",configuration={},configuration_hash=str(i)*64,
            status="complete",chunks_requested=1,chunks_completed=1,chunks_failed=0,
            completed_at=now+timedelta(seconds=i)) for i in (1,2)]
        db.add_all(runs); db.flush()
        assert resolve_retrieval_scope(db,collection_code="pin-test",model_name=model.model_name).index_run.id==runs[1].id
        assert resolve_retrieval_scope(db,collection_code="pin-test",index_run_id=runs[0].id).index_run.id==runs[0].id
        for options in ({"index_run_id":uuid4()},
                        {"index_run_id":runs[0].id,"collection_code":"wrong"},
                        {"index_run_id":runs[0].id,"language_code":"hi"},
                        {"index_run_id":runs[0].id,"model_name":"qwen3-embedding:8b"}):
            with pytest.raises(ValueError,match="Pinned retrieval index"):
                resolve_retrieval_scope(db,**{"collection_code":"pin-test",**options})
        runs[0].status="failed"; db.flush()
        with pytest.raises(ValueError,match="no fallback"):
            resolve_retrieval_scope(db,collection_code="pin-test",index_run_id=runs[0].id)
        runs[0].status="complete"
        runs[0].chunks_completed=0; db.flush()
        with pytest.raises(ValueError,match="incompatible or incomplete"):
            resolve_retrieval_scope(db,collection_code="pin-test",index_run_id=runs[0].id)
        runs[0].chunks_completed=1; model.model_revision="mutable-tag"; db.flush()
        with pytest.raises(ValueError,match="incompatible or incomplete"):
            resolve_retrieval_scope(db,collection_code="pin-test",index_run_id=runs[0].id)
        db.rollback()
    engine.dispose()
