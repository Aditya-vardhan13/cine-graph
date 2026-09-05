"""Application use case for source-linked narrative evidence retrieval."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import EmbeddingIndexRun, EmbeddingModel, EvidenceChunk, EvidenceEmbedding
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.retrieval_routing import (
    RetrievalLane,
    narrative_section_candidates,
    route_research_question,
)


@dataclass(frozen=True)
class RetrievedEvidence:
    chunk_id: str
    subject_entity_id: str
    source_snapshot_id: str
    section_locator: str
    section_title: str
    content: str
    similarity: float


@dataclass(frozen=True)
class RetrievalResult:
    lane: str
    reason: str
    index_run_id: str
    query_embedding_milliseconds: float
    database_ranking_milliseconds: float
    evidence: tuple[RetrievedEvidence, ...]


def _active_index(db: Session, *, model_name: str) -> tuple[EmbeddingIndexRun, EmbeddingModel]:
    row = db.execute(
        select(EmbeddingIndexRun, EmbeddingModel)
        .join(EmbeddingModel, EmbeddingModel.id == EmbeddingIndexRun.embedding_model_id)
        .where(
            EmbeddingIndexRun.status == "complete",
            EmbeddingModel.provider == "ollama",
            EmbeddingModel.model_name == model_name,
        )
        .order_by(EmbeddingIndexRun.completed_at.desc())
    ).first()
    if row is None:
        raise ValueError(f"No complete local embedding index exists for {model_name!r}.")
    return row


def retrieve_narrative_evidence(
    db: Session,
    *,
    subject_entity_id: UUID,
    question_id: str,
    question_text: str,
    evidence_class: str = "narrative_extraction",
    limit: int = 10,
    client: OllamaEmbeddingClient | None = None,
    model_name: str = "qwen3-embedding:0.6b",
) -> RetrievalResult:
    """Embed one question, then rank only eligible evidence for its film/route."""
    route = route_research_question(question_id=question_id, evidence_class=evidence_class)
    if route.primary != RetrievalLane.NARRATIVE_SEMANTIC:
        raise ValueError(f"Question belongs to the {route.primary.value!r} lane, not narrative semantic retrieval.")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    index_run, model = _active_index(db, model_name=model_name)
    profile = OllamaEmbeddingProfile(
        model=model.model_name,
        dimensions=model.dimension,
        query_instruction=model.query_instruction,
    )
    adapter = client or OllamaEmbeddingClient()
    embedding_started = perf_counter()
    query_vector = adapter.embed([profile.query_input(question_text)], profile=profile)[0]
    embedding_milliseconds = (perf_counter() - embedding_started) * 1000

    distance = EvidenceEmbedding.embedding.cosine_distance(query_vector)
    statement = (
        select(EvidenceChunk, distance.label("distance"))
        .join(EvidenceEmbedding, EvidenceEmbedding.evidence_chunk_id == EvidenceChunk.id)
        .where(
            EvidenceEmbedding.index_run_id == index_run.id,
            EvidenceChunk.subject_entity_id == subject_entity_id,
            EvidenceChunk.quality_status == "eligible",
        )
    )
    section_candidates = narrative_section_candidates(question_id=question_id, evidence_class=evidence_class)
    if section_candidates:
        lowered_locator = func.lower(EvidenceChunk.section_locator)
        statement = statement.where(or_(*[
            or_(lowered_locator == section, lowered_locator.like(f"%/{section}"), lowered_locator.like(f"{section}/%"))
            for section in section_candidates
        ]))
    ranking_started = perf_counter()
    rows = db.execute(statement.order_by(distance).limit(limit)).all()
    ranking_milliseconds = (perf_counter() - ranking_started) * 1000
    return RetrievalResult(
        lane=route.primary.value,
        reason=route.reason,
        index_run_id=str(index_run.id),
        query_embedding_milliseconds=round(embedding_milliseconds, 3),
        database_ranking_milliseconds=round(ranking_milliseconds, 3),
        evidence=tuple(
            RetrievedEvidence(
                chunk_id=str(chunk.id),
                subject_entity_id=str(chunk.subject_entity_id),
                source_snapshot_id=str(chunk.source_snapshot_id),
                section_locator=chunk.section_locator,
                section_title=chunk.section_title,
                content=chunk.content,
                similarity=round(1.0 - float(row_distance), 6),
            )
            for chunk, row_distance in rows
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve source-linked narrative evidence from the local index.")
    parser.add_argument("subject_entity_id")
    parser.add_argument("question_id")
    parser.add_argument("question_text")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--model", default="qwen3-embedding:0.6b")
    arguments = parser.parse_args()
    with SessionLocal() as db:
        result = retrieve_narrative_evidence(
            db,
            subject_entity_id=UUID(arguments.subject_entity_id),
            question_id=arguments.question_id,
            question_text=arguments.question_text,
            limit=arguments.limit,
            model_name=arguments.model,
        )
    print(json.dumps({
        "lane": result.lane,
        "reason": result.reason,
        "index_run_id": result.index_run_id,
        "query_embedding_milliseconds": result.query_embedding_milliseconds,
        "database_ranking_milliseconds": result.database_ranking_milliseconds,
        "evidence": [item.__dict__ for item in result.evidence],
    }, indent=2))


if __name__ == "__main__":
    main()
