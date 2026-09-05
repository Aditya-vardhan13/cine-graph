"""Persisted lexical, semantic, and hybrid retrieval for narrative evidence.

The service ranks source-linked evidence candidates.  It does not publish a
fact, interpretation, or relationship.  Structured facts continue to use the
``Assertion`` projection instead of this passage-retrieval path.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from time import perf_counter
from uuid import UUID

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.models import EmbeddingIndexRun, EmbeddingModel, EvidenceChunk, EvidenceEmbedding
from app.services.lexical_retrieval import weighted_reciprocal_rank_fusion
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.retrieval_routing import RetrievalLane, narrative_section_candidates, route_research_question


_LEXICAL_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does", "for", "from",
    "how", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their", "to",
    "was", "were", "what", "when", "which", "while", "who", "why", "with",
})


def lexical_tsquery(question_text: str) -> str:
    """Build a safe OR query; evidence passages need not repeat every prompt term."""
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z0-9]+", question_text.casefold()):
        if len(token) > 1 and token not in _LEXICAL_STOPWORDS and token not in terms:
            terms.append(token)
    return " | ".join(terms) or "cinegraph"


class NarrativeRetrievalMethod(str, Enum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class HybridRetrievedEvidence:
    chunk_id: str
    subject_entity_id: str
    source_snapshot_id: str
    section_locator: str
    section_title: str
    content: str
    rank: int
    fused_score: float | None
    semantic_similarity: float | None
    lexical_score: float | None
    matched_by: tuple[str, ...]


@dataclass(frozen=True)
class HybridRetrievalResult:
    lane: str
    method: str
    reason: str
    index_run_id: str | None
    query_embedding_milliseconds: float
    database_ranking_milliseconds: float
    evidence: tuple[HybridRetrievedEvidence, ...]


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


def _section_conditions(*, question_id: str, evidence_class: str):
    section_candidates = narrative_section_candidates(question_id=question_id, evidence_class=evidence_class)
    if not section_candidates:
        return ()
    lowered_locator = func.lower(EvidenceChunk.section_locator)
    return tuple(
        or_(
            lowered_locator == section,
            lowered_locator.like(f"%/{section}"),
            lowered_locator.like(f"{section}/%"),
        )
        for section in section_candidates
    )


def _lexical_rows(
    db: Session,
    *,
    subject_entity_id: UUID,
    question_id: str,
    question_text: str,
    evidence_class: str,
    candidate_limit: int,
) -> list[tuple[EvidenceChunk, float]]:
    english = literal_column("'english'::regconfig")
    query = func.to_tsquery(english, lexical_tsquery(question_text))
    document = func.to_tsvector(english, EvidenceChunk.section_title + " " + EvidenceChunk.content)
    score = func.ts_rank_cd(document, query)
    statement = select(EvidenceChunk, score.label("lexical_score")).where(
        EvidenceChunk.subject_entity_id == subject_entity_id,
        EvidenceChunk.quality_status == "eligible",
        score > 0,
    )
    section_conditions = _section_conditions(question_id=question_id, evidence_class=evidence_class)
    if section_conditions:
        statement = statement.where(or_(*section_conditions))
    return [(chunk, float(row_score)) for chunk, row_score in db.execute(
        statement.order_by(score.desc(), EvidenceChunk.id).limit(candidate_limit)
    ).all()]


def _semantic_rows(
    db: Session,
    *,
    index_run: EmbeddingIndexRun,
    subject_entity_id: UUID,
    question_id: str,
    query_vector: list[float],
    evidence_class: str,
    candidate_limit: int,
) -> list[tuple[EvidenceChunk, float]]:
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
    section_conditions = _section_conditions(question_id=question_id, evidence_class=evidence_class)
    if section_conditions:
        statement = statement.where(or_(*section_conditions))
    return [(chunk, 1.0 - float(distance_value)) for chunk, distance_value in db.execute(
        statement.order_by(distance, EvidenceChunk.id).limit(candidate_limit)
    ).all()]


def _fused_scores(
    rankings: tuple[list[str], ...], *, weights: tuple[float, ...] | None = None, constant: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    active_weights = weights or tuple(1.0 for _ in rankings)
    if len(active_weights) != len(rankings):
        raise ValueError("Each ranking requires one fusion weight.")
    for ranking, weight in zip(rankings, active_weights, strict=True):
        for rank, identifier in enumerate(ranking, start=1):
            scores[identifier] = scores.get(identifier, 0.0) + weight / (constant + rank)
    return scores


def retrieve_narrative_candidates(
    db: Session,
    *,
    subject_entity_id: UUID,
    question_id: str,
    question_text: str,
    evidence_class: str = "narrative_extraction",
    method: NarrativeRetrievalMethod = NarrativeRetrievalMethod.HYBRID,
    limit: int = 10,
    candidate_limit: int = 50,
    client: OllamaEmbeddingClient | None = None,
    model_name: str = "qwen3-embedding:0.6b",
    query_vector: list[float] | None = None,
) -> HybridRetrievalResult:
    """Rank one film's eligible narrative evidence using the requested method."""
    route = route_research_question(question_id=question_id, evidence_class=evidence_class)
    if route.primary != RetrievalLane.NARRATIVE_SEMANTIC:
        raise ValueError(f"Question belongs to the {route.primary.value!r} lane, not narrative retrieval.")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if not limit <= candidate_limit <= 200:
        raise ValueError("candidate_limit must be between limit and 200")

    index_run: EmbeddingIndexRun | None = None
    model: EmbeddingModel | None = None
    embedding_milliseconds = 0.0
    if method in {NarrativeRetrievalMethod.SEMANTIC, NarrativeRetrievalMethod.HYBRID}:
        index_run, model = _active_index(db, model_name=model_name)
        profile = OllamaEmbeddingProfile(
            model=model.model_name,
            dimensions=model.dimension,
            query_instruction=model.query_instruction,
        )
        if query_vector is None:
            embedding_started = perf_counter()
            query_vector = (client or OllamaEmbeddingClient()).embed(
                [profile.query_input(question_text)], profile=profile,
            )[0]
            embedding_milliseconds = (perf_counter() - embedding_started) * 1000
        elif len(query_vector) != model.dimension:
            raise ValueError(
                f"Precomputed query vector has {len(query_vector)} dimensions; expected {model.dimension}."
            )

    ranking_started = perf_counter()
    lexical_rows = _lexical_rows(
        db,
        subject_entity_id=subject_entity_id,
        question_id=question_id,
        question_text=question_text,
        evidence_class=evidence_class,
        candidate_limit=candidate_limit,
    ) if method in {NarrativeRetrievalMethod.LEXICAL, NarrativeRetrievalMethod.HYBRID} else []
    semantic_rows = _semantic_rows(
        db,
        index_run=index_run,
        subject_entity_id=subject_entity_id,
        question_id=question_id,
        query_vector=query_vector,
        evidence_class=evidence_class,
        candidate_limit=candidate_limit,
    ) if index_run is not None and query_vector is not None else []

    lexical_ids = [str(chunk.id) for chunk, _ in lexical_rows]
    semantic_ids = [str(chunk.id) for chunk, _ in semantic_rows]
    if method == NarrativeRetrievalMethod.LEXICAL:
        ranked_ids = lexical_ids[:limit]
        fused = {}
    elif method == NarrativeRetrievalMethod.SEMANTIC:
        ranked_ids = semantic_ids[:limit]
        fused = {}
    else:
        ranked_ids = weighted_reciprocal_rank_fusion(
            ((semantic_ids, 3.0), (lexical_ids, 1.0)), cutoff=limit,
        )
        fused = _fused_scores((semantic_ids, lexical_ids), weights=(3.0, 1.0))
    ranking_milliseconds = (perf_counter() - ranking_started) * 1000

    chunks = {str(chunk.id): chunk for chunk, _ in (*semantic_rows, *lexical_rows)}
    semantic_scores = {str(chunk.id): score for chunk, score in semantic_rows}
    lexical_scores = {str(chunk.id): score for chunk, score in lexical_rows}
    evidence = tuple(
        HybridRetrievedEvidence(
            chunk_id=identifier,
            subject_entity_id=str(chunks[identifier].subject_entity_id),
            source_snapshot_id=str(chunks[identifier].source_snapshot_id),
            section_locator=chunks[identifier].section_locator,
            section_title=chunks[identifier].section_title,
            content=chunks[identifier].content,
            rank=rank,
            fused_score=round(fused[identifier], 8) if identifier in fused else None,
            semantic_similarity=round(semantic_scores[identifier], 6) if identifier in semantic_scores else None,
            lexical_score=round(lexical_scores[identifier], 6) if identifier in lexical_scores else None,
            matched_by=tuple(
                lane for lane, scores in (("semantic", semantic_scores), ("lexical", lexical_scores))
                if identifier in scores
            ),
        )
        for rank, identifier in enumerate(ranked_ids, start=1)
    )
    return HybridRetrievalResult(
        lane=route.primary.value,
        method=method.value,
        reason=route.reason,
        index_run_id=str(index_run.id) if index_run is not None else None,
        query_embedding_milliseconds=round(embedding_milliseconds, 3),
        database_ranking_milliseconds=round(ranking_milliseconds, 3),
        evidence=evidence,
    )
