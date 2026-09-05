"""Real HTTP and PostgreSQL contract checks for the isolated local stack."""
from __future__ import annotations

import os
import hashlib

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models import EmbeddingIndexRun, EmbeddingModel, EvidenceChunk, EvidenceEmbedding
from app.services.evidence_preprocessing import build_evidence_chunks, evidence_chunk_quality_report

API_URL = os.environ.get("CINEGRAPH_INTEGRATION_API_URL", "http://127.0.0.1:8001")
DATABASE_URL = os.environ.get(
    "CINEGRAPH_TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/cinegraph_test",
)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("CINEGRAPH_RUN_INTEGRATION") != "1",
        reason="run through scripts/run_integration_tests.sh against the isolated local stack",
    ),
]


def api_get(path: str) -> httpx.Response:
    return httpx.get(f"{API_URL}{path}", timeout=5.0)


def test_health_and_catalogue_are_served_from_real_postgresql() -> None:
    response = api_get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["films"] == 2
    assert payload["language_editions"] == [{
        "code": "en", "display_name": "English", "native_name": "English",
        "script": "Latin", "enabled": True, "status": "live", "transliteration_strategy": None,
    }]

    with create_engine(DATABASE_URL).connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM films")) == 2
        assert connection.scalar(text("SELECT count(*) FROM film_provenance")) == 2
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260901_13"
        assert connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")) is True
        assert connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")) is True
        assert connection.scalar(text("SELECT to_regclass('public.ix_films_canonical_title_trgm')")) == "ix_films_canonical_title_trgm"


def test_search_detail_comparison_and_lineage_return_evidence_backed_contracts() -> None:
    search = api_get("/api/v1/films?q=dark&limit=5")
    assert search.status_code == 200
    items = search.json()
    assert [item["title"] for item in items] == ["The Dark Knight"]
    knight_id = items[0]["id"]

    detail = api_get(f"/api/v1/films/{knight_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["credits"] == [{
        "person_id": detail_payload["credits"][0]["person_id"],
        "name": "Christopher Nolan", "role": "director", "character_name": None,
    }]
    assert detail_payload["provenance"] == [{
        "source_name": "Integration fixture source",
        "source_url": "https://example.test/cinegraph-fixture",
        "license": "CC0 1.0",
        "field_name": "canonical_title",
        "source_reference": "https://www.wikidata.org/wiki/Q163872",
    }]

    begins = api_get("/api/v1/films?q=begins&limit=5").json()[0]
    comparison = api_get(f"/api/v1/films/compare?first_id={begins['id']}&second_id={knight_id}")
    assert comparison.status_code == 200
    labels = {signal["label"] for signal in comparison.json()["signals"]}
    assert labels == {"Shared genres", "Shared creative collaborators", "Release era"}

    lineage = api_get(f"/api/v1/films/{begins['id']}/lineage")
    assert lineage.status_code == 200
    edges = lineage.json()["edges"]
    assert len(edges) == 1
    assert edges[0]["target_title"] == "The Dark Knight"
    assert edges[0]["evidence_url"] == "https://www.wikidata.org/wiki/Q163872"


def test_preprocessing_uses_real_postgresql_rows_and_preserves_narrative_lineage() -> None:
    with Session(create_engine(DATABASE_URL)) as db:
        first = build_evidence_chunks(db, collection_code="integration-narrative-v1")
        second = build_evidence_chunks(db, collection_code="integration-narrative-v1")
        report = evidence_chunk_quality_report(db, collection_code="integration-narrative-v1")

    assert first["passages_requested"] == 1
    assert first["passages_eligible"] == 1
    assert first["chunks_created"] + first["chunks_reused"] >= 1
    assert second["chunks_created"] == 0
    assert second["chunks_reused"] >= 1
    assert report["quality_status_counts"]["eligible"] >= 1
    assert report["eligible_chunks_per_film"]["films_with_eligible_chunks"] == 1

    with create_engine(DATABASE_URL).connect() as connection:
        row = connection.execute(text(
            "SELECT chunk.source_snapshot_id = passage.source_snapshot_id "
            "FROM evidence_chunks AS chunk "
            "JOIN narrative_passages AS passage ON passage.id = chunk.narrative_passage_id "
            "WHERE chunk.quality_status = 'eligible'"
        )).scalar_one()
        assert row is True


def test_pgvector_index_preserves_chunk_lineage_and_cosine_ordering() -> None:
    instruction = "Retrieve direct source evidence."
    instruction_digest = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
    vector = [1.0] + [0.0] * 1023
    with Session(create_engine(DATABASE_URL)) as db:
        build_evidence_chunks(db, collection_code="integration-narrative-v1")
        chunk = db.scalar(text("SELECT id FROM evidence_chunks WHERE quality_status = 'eligible' LIMIT 1"))
        chunk_run = db.scalar(text("SELECT preprocessing_run_id FROM evidence_chunks WHERE id = :id"), {"id": chunk})
        content_hash = db.scalar(text("SELECT content_hash FROM evidence_chunks WHERE id = :id"), {"id": chunk})
        model = EmbeddingModel(
            provider="test-local", model_name="fixture-embedding", model_revision="fixture-v1",
            dimension=1024, query_instruction=instruction, instruction_hash=instruction_digest,
            license="test-fixture",
        )
        db.add(model)
        db.flush()
        index_run = EmbeddingIndexRun(
            evidence_chunk_run_id=chunk_run, embedding_model_id=model.id,
            document_representation="film-section-evidence-v1",
            configuration={"fixture": True}, configuration_hash="a" * 64,
            status="complete", chunks_requested=1, chunks_completed=1,
        )
        db.add(index_run)
        db.flush()
        embedding = EvidenceEmbedding(
            index_run_id=index_run.id, evidence_chunk_id=chunk,
            content_hash=content_hash, embedding=vector,
        )
        db.add(embedding)
        db.commit()

        distance = EvidenceEmbedding.embedding.cosine_distance(vector)
        row = db.execute(
            select(EvidenceEmbedding.evidence_chunk_id, distance)
            .where(EvidenceEmbedding.index_run_id == index_run.id)
            .order_by(distance)
        ).one()

    assert row.evidence_chunk_id == chunk
    assert abs(float(row[1])) < 1e-6
