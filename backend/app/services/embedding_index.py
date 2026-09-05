"""Materialise a validated local embedding artifact into PostgreSQL/pgvector."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    CanonicalEntity,
    EmbeddingIndexRun,
    EmbeddingModel,
    EvidenceChunk,
    EvidenceChunkRun,
    EvidenceEmbedding,
)
from app.services.embedding_artifacts import (
    DOCUMENT_REPRESENTATION,
    STORAGE_DIMENSION,
    document_cache_key,
    embedding_configuration_hash,
)
from app.services.ollama_embeddings import QWEN_FILM_RETRIEVAL_INSTRUCTION


def instruction_hash(instruction: str) -> str:
    return hashlib.sha256(instruction.encode("utf-8")).hexdigest()


def _candidate_run(db: Session, *, collection_code: str, chunker_version: str) -> EvidenceChunkRun:
    run = db.scalar(select(EvidenceChunkRun).where(
        EvidenceChunkRun.collection_code == collection_code,
        EvidenceChunkRun.chunker_version == chunker_version,
        EvidenceChunkRun.status == "complete",
    ).order_by(EvidenceChunkRun.completed_at.desc()))
    if run is None:
        raise ValueError("No completed evidence chunk run matches the requested collection and version.")
    return run


def _ordered_chunks_and_contents(
    db: Session, run: EvidenceChunkRun,
) -> tuple[list[EvidenceChunk], list[str]]:
    chunks = list(db.scalars(select(EvidenceChunk).where(
        EvidenceChunk.preprocessing_run_id == run.id,
        EvidenceChunk.quality_status == "eligible",
    ).order_by(EvidenceChunk.id)))
    labels = dict(db.execute(select(CanonicalEntity.id, CanonicalEntity.canonical_label).where(
        CanonicalEntity.id.in_({chunk.subject_entity_id for chunk in chunks})
    )).all())
    contents = [
        f"Film: {labels[chunk.subject_entity_id]}\nSection: {chunk.section_title}\nEvidence: {chunk.content}"
        for chunk in chunks
    ]
    return chunks, contents


def _model_record(
    db: Session,
    *,
    model_name: str,
    model_revision: str,
    dimension: int,
    query_instruction: str,
) -> EmbeddingModel:
    digest = instruction_hash(query_instruction)
    record = db.scalar(select(EmbeddingModel).where(
        EmbeddingModel.provider == "ollama",
        EmbeddingModel.model_name == model_name,
        EmbeddingModel.model_revision == model_revision,
        EmbeddingModel.dimension == dimension,
        EmbeddingModel.instruction_hash == digest,
    ))
    if record is not None:
        return record
    record = EmbeddingModel(
        provider="ollama",
        model_name=model_name,
        model_revision=model_revision,
        dimension=dimension,
        query_instruction=query_instruction,
        instruction_hash=digest,
        license="Apache-2.0",
    )
    db.add(record)
    db.flush()
    return record


def import_embedding_cache(
    db: Session,
    *,
    cache_path: Path,
    collection_code: str,
    chunker_version: str,
    model_name: str,
    model_revision: str,
    dimension: int = STORAGE_DIMENSION,
    query_instruction: str = QWEN_FILM_RETRIEVAL_INSTRUCTION,
    batch_size: int = 250,
) -> EmbeddingIndexRun:
    """Import an exact evaluator cache, resuming safely after each DB batch."""
    if dimension != STORAGE_DIMENSION:
        raise ValueError(f"The v1 pgvector index requires {STORAGE_DIMENSION} dimensions.")
    run = _candidate_run(db, collection_code=collection_code, chunker_version=chunker_version)
    chunks, contents = _ordered_chunks_and_contents(db, run)
    expected_cache_key = document_cache_key(
        provider="ollama",
        model_name=model_name,
        dimensions=dimension,
        chunk_run_id=str(run.id),
        chunker_version=run.chunker_version,
        contents=contents,
    )
    if expected_cache_key not in cache_path.name:
        raise ValueError("Embedding cache identity does not match this model, chunk run, and document representation.")
    matrix = np.load(cache_path, mmap_mode="r", allow_pickle=False)
    if matrix.shape != (len(chunks), dimension) or matrix.dtype != np.float32:
        raise ValueError(f"Embedding cache has shape/dtype {matrix.shape}/{matrix.dtype}; expected {(len(chunks), dimension)}/float32.")

    model = _model_record(
        db,
        model_name=model_name,
        model_revision=model_revision,
        dimension=dimension,
        query_instruction=query_instruction,
    )
    configuration_hash = embedding_configuration_hash(
        model_name=model_name,
        model_revision=model_revision,
        dimension=dimension,
        instruction_hash=model.instruction_hash,
    )
    index_run = db.scalar(select(EmbeddingIndexRun).where(
        EmbeddingIndexRun.evidence_chunk_run_id == run.id,
        EmbeddingIndexRun.embedding_model_id == model.id,
        EmbeddingIndexRun.configuration_hash == configuration_hash,
    ))
    if index_run is None:
        index_run = EmbeddingIndexRun(
            evidence_chunk_run_id=run.id,
            embedding_model_id=model.id,
            document_representation=DOCUMENT_REPRESENTATION,
            configuration={
                "cache_key": expected_cache_key,
                "dimension": dimension,
                "overflow_policy": "ollama_truncate_false",
            },
            configuration_hash=configuration_hash,
            status="running",
            chunks_requested=len(chunks),
        )
        db.add(index_run)
        db.commit()
    elif index_run.status == "complete" and index_run.chunks_completed == len(chunks):
        return index_run
    else:
        index_run.status = "running"
        index_run.error_summary = None
        db.commit()

    persisted_chunk_ids = set(db.scalars(select(EvidenceEmbedding.evidence_chunk_id).where(
        EvidenceEmbedding.index_run_id == index_run.id,
    )))
    completed_count = len(persisted_chunk_ids)
    try:
        for offset in range(0, len(chunks), batch_size):
            pending = [
                (chunk, matrix[index].tolist())
                for index, chunk in enumerate(chunks[offset: offset + batch_size], start=offset)
                if chunk.id not in persisted_chunk_ids
            ]
            db.add_all([
                EvidenceEmbedding(
                    index_run_id=index_run.id,
                    evidence_chunk_id=chunk.id,
                    content_hash=chunk.content_hash,
                    embedding=vector,
                )
                for chunk, vector in pending
            ])
            completed_count += len(pending)
            index_run.chunks_completed = completed_count
            db.commit()
            print(f"[{model_name}] pgvector rows: {index_run.chunks_completed:,}/{len(chunks):,}", flush=True)
        index_run.status = "complete"
        index_run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return index_run
    except Exception as exc:
        db.rollback()
        failed_run = db.get(EmbeddingIndexRun, index_run.id)
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_summary = str(exc)[:2000]
            db.commit()
        raise


def index_status(db: Session, index_run_id: str) -> dict[str, Any]:
    run = db.get(EmbeddingIndexRun, UUID(index_run_id))
    if run is None:
        raise ValueError("Embedding index run does not exist.")
    return {
        "index_run_id": str(run.id),
        "status": run.status,
        "chunks_requested": run.chunks_requested,
        "chunks_completed": run.chunks_completed,
        "chunks_failed": run.chunks_failed,
        "progress_percent": round((run.chunks_completed / run.chunks_requested * 100), 2) if run.chunks_requested else 0.0,
        "error_summary": run.error_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a validated local vector cache into pgvector.")
    parser.add_argument("cache_path")
    parser.add_argument("--collection", default="english-1000-retained-narrative-v1")
    parser.add_argument("--chunker-version", default="spacy-sentencizer-evidence-v3")
    parser.add_argument("--model", default="qwen3-embedding:0.6b")
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--dimension", type=int, default=STORAGE_DIMENSION)
    parser.add_argument("--batch-size", type=int, default=250)
    arguments = parser.parse_args()
    with SessionLocal() as db:
        run = import_embedding_cache(
            db,
            cache_path=Path(arguments.cache_path),
            collection_code=arguments.collection,
            chunker_version=arguments.chunker_version,
            model_name=arguments.model,
            model_revision=arguments.model_revision,
            dimension=arguments.dimension,
            batch_size=arguments.batch_size,
        )
        print(json.dumps(index_status(db, str(run.id)), indent=2))


if __name__ == "__main__":
    main()
