"""Bounded, source-attributed browsing of one film's active evidence corpus.

This is a reading surface. Chunks remain narrative context, never reviewed facts.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import EvidenceChunk, ReferenceCollection, SourceSnapshot
from app.services.retrieval_scope import resolve_retrieval_scope


SECTIONS = frozenset({"plot", "production", "reception", "themes", "legacy"})


@dataclass(frozen=True)
class FilmPassage:
    chunk_id: UUID
    section_title: str
    section_locator: str
    excerpt: str
    source_url: str
    source_revision: str | None
    source_license: str


@dataclass(frozen=True)
class FilmPassagePage:
    total: int
    preprocessing_run_id: UUID
    passages: tuple[FilmPassage, ...]


def browse_research_passages(
    db: Session, *, entity_id: UUID, collection_code: str,
    section: str, limit: int, offset: int,
) -> FilmPassagePage:
    if section not in SECTIONS:
        raise ValueError("Unsupported research section")
    if not 1 <= limit <= 20 or not 0 <= offset <= 1000:
        raise ValueError("Passage page is outside the supported bounds")
    language_code = db.scalar(select(ReferenceCollection.language_code).where(ReferenceCollection.code == collection_code))
    if language_code is None:
        raise ValueError("Research collection is unavailable")
    scope = resolve_retrieval_scope(db, collection_code=collection_code, language_code=language_code)
    conditions = (
        EvidenceChunk.subject_entity_id == entity_id,
        EvidenceChunk.preprocessing_run_id == scope.preprocessing_run_id,
        EvidenceChunk.quality_status == "eligible",
    )
    section_condition = (
        EvidenceChunk.section_locator.like("themes%")
        if section == "themes" else
        or_(EvidenceChunk.section_locator == section,
            EvidenceChunk.section_locator.like(f"{section}/%"))
    )
    total = db.scalar(select(func.count(EvidenceChunk.id)).where(*conditions, section_condition)) or 0
    rows = db.execute(
        select(EvidenceChunk, SourceSnapshot)
        .join(SourceSnapshot, SourceSnapshot.id == EvidenceChunk.source_snapshot_id)
        .where(*conditions, section_condition)
        .order_by(EvidenceChunk.section_locator, EvidenceChunk.chunk_ordinal, EvidenceChunk.id)
        .limit(limit).offset(offset)
    ).all()
    return FilmPassagePage(total=total, preprocessing_run_id=scope.preprocessing_run_id, passages=tuple(
        FilmPassage(
            chunk_id=chunk.id, section_title=chunk.section_title,
            section_locator=chunk.section_locator, excerpt=chunk.content,
            source_url=snapshot.attribution_url or snapshot.canonical_url,
            source_revision=snapshot.source_revision, source_license=snapshot.license,
        ) for chunk, snapshot in rows
    ))
