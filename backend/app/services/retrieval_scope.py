"""Select one immutable corpus version for an entire retrieval request."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmbeddingIndexRun, EmbeddingModel, EvidenceChunkRun


DEFAULT_COLLECTION = "english-1000-retained-narrative-v1"


@dataclass(frozen=True)
class RetrievalScope:
    preprocessing_run_id: UUID
    index_run: EmbeddingIndexRun | None
    model: EmbeddingModel | None


def resolve_retrieval_scope(
    db: Session, *, collection_code: str = DEFAULT_COLLECTION,
    model_name: str = "qwen3-embedding:0.6b", language_code: str = "en",
) -> RetrievalScope:
    """Prefer the indexed corpus, including for lexical-only requests/fallback.

    A completed but not yet embedded preprocessing run must not silently
    replace the text used by the active model. Without an index, lexical
    retrieval can use the latest completed preprocessing run in this collection.
    """
    row = db.execute(
        select(EmbeddingIndexRun, EmbeddingModel)
        .join(EmbeddingModel, EmbeddingModel.id == EmbeddingIndexRun.embedding_model_id)
        .join(EvidenceChunkRun, EvidenceChunkRun.id == EmbeddingIndexRun.evidence_chunk_run_id)
        .where(
            EmbeddingIndexRun.status == "complete", EvidenceChunkRun.status == "complete",
            EvidenceChunkRun.collection_code == collection_code,
            EvidenceChunkRun.language_code == language_code,
            EmbeddingModel.provider == "ollama", EmbeddingModel.model_name == model_name,
        )
        .order_by(EmbeddingIndexRun.completed_at.desc().nulls_last(), EmbeddingIndexRun.id)
    ).first()
    if row is not None:
        index_run, model = row
        return RetrievalScope(index_run.evidence_chunk_run_id, index_run, model)
    chunk_run_id = db.scalar(
        select(EvidenceChunkRun.id).where(
            EvidenceChunkRun.collection_code == collection_code,
            EvidenceChunkRun.language_code == language_code, EvidenceChunkRun.status == "complete",
        ).order_by(EvidenceChunkRun.completed_at.desc().nulls_last(), EvidenceChunkRun.id)
        .limit(1)
    )
    if chunk_run_id is None:
        raise ValueError(f"No completed narrative preprocessing run exists for {collection_code!r}.")
    return RetrievalScope(chunk_run_id, None, None)
