"""Question-first film leads from the existing source-linked narrative index.

This is candidate discovery, not a film relationship or a proven comparison.
One cited passage explains why a title is offered; the writer chooses whether
it belongs in a study pair.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

import httpx
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session, selectinload

from app.models import CanonicalEntity, EvidenceChunk, EvidenceEmbedding, SourceSnapshot
from app.services.comparison_answerability import unmet_source_requirement
from app.services.hybrid_evidence_retrieval import embed_narrative_queries, lexical_tsquery
from app.services.ollama_embeddings import OllamaEmbeddingClient
from app.services.research_catalog import (
    DEFAULT_RESEARCH_COLLECTION, ResearchFilm, research_films_from_entities,
)
from app.services.retrieval_scope import resolve_retrieval_scope


_GENERIC_WORDS = frozenset({
    "film", "films", "movie", "movies", "make", "makes", "different", "which", "what",
    "could", "would", "their", "about", "question", "story", "stories", "human",
})
_TOPIC_CUES = (
    (re.compile(r"\b(?:artificial intelligence|artificial companions?(?:hip)?|a\.i\.|ai)\b", re.I),
     re.compile(r"\b(?:ai|robots?|androids?|replicants?|machines?)\b|operating system", re.I)),
    (re.compile(r"\b(?:heir|throne|succession)\b", re.I),
     re.compile(r"\b(?:heir|successor|throne|princes?|kings?|queens?|inherit|royal|succession)\b", re.I)),
)


def _question_terms(question: str) -> set[str]:
    return set(lexical_tsquery(question).split(" | ")) - _GENERIC_WORDS - {"cinegraph"}


def _passage_alignment(question: str, content: str) -> int:
    """Cheap precision check on candidates, not an answerability judgment."""
    passage_terms = set(re.findall(r"[a-z0-9]+", content.casefold()))
    return len(_question_terms(question) & passage_terms)


def _has_required_topic_cues(question: str, content: str) -> bool:
    return all(cue.search(content) for trigger, cue in _TOPIC_CUES if trigger.search(question))


@dataclass(frozen=True)
class DiscoveryLead:
    film: ResearchFilm
    excerpt: str
    section_title: str
    source_url: str
    source_revision: str | None
    source_license: str
    matched_by: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryResult:
    question: str
    method: str
    degraded: bool
    reason: str
    leads: tuple[DiscoveryLead, ...]
    preprocessing_run_id: str
    index_run_id: str | None


def _lexical_candidates(db: Session, *, question: str, run_id: UUID, limit: int) -> list[EvidenceChunk]:
    english = literal_column("'english'::regconfig")
    query = func.to_tsquery(english, lexical_tsquery(question))
    document = func.to_tsvector(english, EvidenceChunk.section_title + " " + EvidenceChunk.content)
    score = func.ts_rank_cd(document, query)
    return list(db.scalars(select(EvidenceChunk).where(
        EvidenceChunk.preprocessing_run_id == run_id,
        EvidenceChunk.quality_status == "eligible",
        document.op("@@")(query),
    ).order_by(score.desc(), EvidenceChunk.id).limit(limit)).all())


def _semantic_candidates(
    db: Session, *, vector: list[float], index_run_id: UUID, chunk_run_id: UUID, limit: int,
) -> list[EvidenceChunk]:
    distance = EvidenceEmbedding.embedding.cosine_distance(vector)
    return list(db.scalars(
        select(EvidenceChunk)
        .join(EvidenceEmbedding, EvidenceEmbedding.evidence_chunk_id == EvidenceChunk.id)
        .where(
            EvidenceEmbedding.index_run_id == index_run_id,
            EvidenceChunk.preprocessing_run_id == chunk_run_id,
            EvidenceChunk.quality_status == "eligible",
        )
        .order_by(distance, EvidenceChunk.id).limit(limit)
    ).all())


def _rank_leads(
    *, question: str, lexical: list[EvidenceChunk], semantic: list[EvidenceChunk],
    excluded: set[UUID], limit: int,
) -> list[tuple[EvidenceChunk, tuple[str, ...]]]:
    """Weighted rank fusion followed by one source lead per film."""
    scores: dict[UUID, float] = {}
    chunks: dict[UUID, EvidenceChunk] = {}
    methods: dict[UUID, set[str]] = {}
    for name, ranking, weight in (("semantic", semantic, 3.0), ("term_rerank" if semantic else "lexical", lexical, 1.0)):
        for rank, chunk in enumerate(ranking, start=1):
            if chunk.subject_entity_id in excluded:
                continue
            if name == "term_rerank" and not _passage_alignment(question, chunk.content):
                continue
            if not _has_required_topic_cues(question, chunk.content):
                continue
            chunks[chunk.id] = chunk
            scores[chunk.id] = scores.get(chunk.id, 0.0) + weight / (60 + rank)
            methods.setdefault(chunk.id, set()).add(name)
    per_film: dict[UUID, UUID] = {}
    for chunk_id in sorted(
        scores,
        key=lambda identifier: (
            -(scores[identifier] + min(_passage_alignment(question, chunks[identifier].content), 4) * 0.006),
            str(identifier),
        ),
    ):
        film_id = chunks[chunk_id].subject_entity_id
        per_film.setdefault(film_id, chunk_id)
        if len(per_film) >= limit:
            break
    return [
        (chunks[chunk_id], tuple(sorted(methods[chunk_id])))
        for chunk_id in per_film.values()
    ]


def discover_research_films(
    db: Session,
    *,
    question: str,
    exclude_entity_ids: set[UUID] | None = None,
    limit: int = 6,
    collection_code: str = DEFAULT_RESEARCH_COLLECTION,
    embedding_client: OllamaEmbeddingClient | None = None,
) -> DiscoveryResult:
    normalized = question.strip()
    if not 12 <= len(normalized) <= 400:
        raise ValueError("A writing question must contain 12 to 400 characters.")
    if not 1 <= limit <= 12:
        raise ValueError("limit must be between 1 and 12")
    scope = resolve_retrieval_scope(db, collection_code=collection_code)
    requirement = unmet_source_requirement(normalized)
    if requirement is not None:
        return DiscoveryResult(
            question=normalized, method="not_run", degraded=False,
            reason=requirement.explanation, leads=(),
            preprocessing_run_id=str(scope.preprocessing_run_id), index_run_id=None,
        )
    semantic: list[EvidenceChunk] = []
    degraded = False
    if scope.index_run is not None:
        try:
            vector = embed_narrative_queries(
                db, question_texts=[normalized], client=embedding_client, scope=scope,
            )[0]
            semantic = _semantic_candidates(
                db, vector=vector, index_run_id=scope.index_run.id,
                chunk_run_id=scope.preprocessing_run_id, limit=350,
            )
        except (ValueError, RuntimeError, httpx.HTTPError):
            degraded = True
    lexical = (
        sorted(semantic, key=lambda chunk: (-_passage_alignment(normalized, chunk.content), str(chunk.id)))
        if semantic else _lexical_candidates(db, question=normalized, run_id=scope.preprocessing_run_id, limit=250)
    )
    candidates = _rank_leads(
        question=normalized, lexical=lexical, semantic=semantic,
        excluded=exclude_entity_ids or set(), limit=limit,
    )
    entity_ids = [chunk.subject_entity_id for chunk, _ in candidates]
    entities = list(db.scalars(select(CanonicalEntity).options(
        selectinload(CanonicalEntity.film_profile),
    ).where(CanonicalEntity.id.in_(entity_ids), CanonicalEntity.entity_kind == "film")).all())
    films = {film.entity_id: film for film in research_films_from_entities(db, entities)}
    snapshots = {snapshot.id: snapshot for snapshot in db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.id.in_([chunk.source_snapshot_id for chunk, _ in candidates]),
    )).all()}
    leads = tuple(
        DiscoveryLead(
            film=films[chunk.subject_entity_id], excerpt=chunk.content,
            section_title=chunk.section_title,
            source_url=snapshots[chunk.source_snapshot_id].attribution_url or snapshots[chunk.source_snapshot_id].canonical_url,
            source_revision=snapshots[chunk.source_snapshot_id].source_revision,
            source_license=snapshots[chunk.source_snapshot_id].license,
            matched_by=methods,
        )
        for chunk, methods in candidates
        if chunk.subject_entity_id in films and chunk.source_snapshot_id in snapshots
    )
    return DiscoveryResult(
        question=normalized,
        method="semantic_with_term_rerank" if semantic else "lexical",
        degraded=degraded or scope.index_run is None,
        reason=(
            "These are source-linked passage matches to explore, not proven film relationships or complete answers."
        ),
        leads=leads,
        preprocessing_run_id=str(scope.preprocessing_run_id),
        index_run_id=str(scope.index_run.id) if semantic and scope.index_run else None,
    )
