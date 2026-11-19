"""Select one immutable corpus version for an entire retrieval request."""
from dataclasses import dataclass
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmbeddingIndexRun, EmbeddingModel, EvidenceChunkRun
from app.core.config import get_settings
from app.services.ollama_embeddings import MANIFEST_REVISION_PREFIX


DEFAULT_COLLECTION = "english-1000-retained-narrative-v1"


@dataclass(frozen=True)
class RetrievalScope:
    preprocessing_run_id: UUID
    index_run: EmbeddingIndexRun | None
    model: EmbeddingModel | None


def resolve_retrieval_scope(
    db: Session, *, collection_code: str = DEFAULT_COLLECTION,
    model_name: str | None = None, language_code: str = "en",
    index_run_id: UUID | None = None,
) -> RetrievalScope:
    """Prefer the indexed corpus, including for lexical-only requests/fallback.

    A completed but not yet embedded preprocessing run must not silently
    replace the text used by the active model. Without an index, lexical
    retrieval can use the latest completed preprocessing run in this collection.
    """
    # Explicit model requests are offline comparisons and do not inherit a
    # serving activation. Normal callers share one configured immutable run.
    pinned_id = index_run_id or (get_settings().active_retrieval_index_run_id if model_name is None else None)
    model_filters = (EmbeddingIndexRun.id == pinned_id,) if pinned_id else (
        EmbeddingModel.model_name == (model_name or "qwen3-embedding:0.6b"),)
    row = db.execute(
        select(EmbeddingIndexRun, EmbeddingModel)
        .join(EmbeddingModel, EmbeddingModel.id == EmbeddingIndexRun.embedding_model_id)
        .join(EvidenceChunkRun, EvidenceChunkRun.id == EmbeddingIndexRun.evidence_chunk_run_id)
        .where(
            EmbeddingIndexRun.status == "complete", EvidenceChunkRun.status == "complete",
            EvidenceChunkRun.collection_code == collection_code,
            EvidenceChunkRun.language_code == language_code,
            EmbeddingModel.provider == "ollama", *model_filters,
        )
        .order_by(EmbeddingIndexRun.completed_at.desc().nulls_last(), EmbeddingIndexRun.id)
    ).first()
    if row is not None:
        index_run, model = row
        if pinned_id:
            if (model_name is not None and model.model_name != model_name
                or model.dimension != 1024
                or not re.fullmatch(re.escape(MANIFEST_REVISION_PREFIX)+r"[0-9a-f]{64}",model.model_revision)
                or index_run.chunks_requested < 1
                or index_run.chunks_completed != index_run.chunks_requested
                or index_run.chunks_failed != 0):
                raise ValueError("Pinned retrieval index has an incompatible or incomplete embedding contract.")
        return RetrievalScope(index_run.evidence_chunk_run_id, index_run, model)
    if pinned_id:
        raise ValueError("Pinned retrieval index is unavailable for this collection and language; no fallback selected.")
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
