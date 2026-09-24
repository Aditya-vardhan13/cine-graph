"""Reuse persisted vectors only when the indexed document inputs are identical."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, insert, literal, select
from sqlalchemy.orm import Session, aliased

from app.db import SessionLocal
from app.models import (
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
from app.services.embedding_index import _ordered_chunks_and_contents


def _source_and_target(db: Session, source_index_id: UUID, target_chunk_run_id: UUID):
    source_index = db.get(EmbeddingIndexRun, source_index_id)
    target_run = db.get(EvidenceChunkRun, target_chunk_run_id)
    if source_index is None or target_run is None:
        raise ValueError("The source index run or target chunk run does not exist.")
    source_run = db.get(EvidenceChunkRun, source_index.evidence_chunk_run_id)
    model = db.get(EmbeddingModel, source_index.embedding_model_id)
    if source_run is None or model is None:
        raise ValueError("The source index is missing its chunk run or model record.")
    if source_index.status != "complete" or source_index.chunks_completed != source_index.chunks_requested:
        raise ValueError("Only a complete source index can be reused.")
    if target_run.status != "complete":
        raise ValueError("The target chunk run must be complete before vector reuse.")
    if source_index.document_representation != DOCUMENT_REPRESENTATION:
        raise ValueError("The source index uses an unsupported document representation.")
    if model.dimension != STORAGE_DIMENSION:
        raise ValueError("The source model dimension does not match the local pgvector schema.")
    if (source_run.collection_code, source_run.language_code) != (target_run.collection_code, target_run.language_code):
        raise ValueError("Vector reuse requires the same collection and language edition.")

    source_chunks, source_contents = _ordered_chunks_and_contents(db, source_run)
    recorded_key = source_index.configuration.get("cache_key")
    expected_key = document_cache_key(
        provider=model.provider,
        model_name=model.model_name,
        dimensions=model.dimension,
        chunk_run_id=str(source_run.id),
        chunker_version=source_run.chunker_version,
        contents=source_contents,
        representation=source_index.document_representation,
    )
    if not recorded_key or recorded_key != expected_key:
        raise ValueError("The source index cache key no longer verifies its exact original document inputs.")

    source_vector_count = db.scalar(select(func.count()).select_from(EvidenceEmbedding).where(
        EvidenceEmbedding.index_run_id == source_index.id,
    )) or 0
    if source_vector_count != len(source_chunks) or source_vector_count != source_index.chunks_completed:
        raise ValueError("The source index does not have exactly one vector for every eligible source chunk.")
    return source_index, source_run, target_run, model, recorded_key, len(source_chunks)


def plan_exact_embedding_reuse(
    db: Session,
    *,
    source_index_id: UUID,
    target_chunk_run_id: UUID,
) -> dict[str, Any]:
    """Read-only preflight; fails closed unless every target has a 1:1 exact input match."""
    source_index, source_run, target_run, model, source_cache_key, source_count = _source_and_target(
        db, source_index_id, target_chunk_run_id,
    )
    target_count = db.scalar(select(func.count()).select_from(EvidenceChunk).where(
        EvidenceChunk.preprocessing_run_id == target_run.id,
        EvidenceChunk.quality_status == "eligible",
    )) or 0
    if target_count == 0 or target_count != source_count:
        raise ValueError("Source and target runs must have the same non-zero eligible chunk count.")

    target = aliased(EvidenceChunk)
    source = aliased(EvidenceChunk)
    source_vector = aliased(EvidenceEmbedding)
    exact_inputs = and_(
        target.content_hash == source.content_hash,
        target.content == source.content,
        target.section_title == source.section_title,
        target.subject_entity_id == source.subject_entity_id,
        target.language_code == source.language_code,
    )
    pairs = (
        select(target.id.label("target_id"), source.id.label("source_id"))
        .select_from(target)
        .join(source, exact_inputs)
        .join(source_vector, and_(
            source_vector.evidence_chunk_id == source.id,
            source_vector.index_run_id == source_index.id,
        ))
        .where(
            target.preprocessing_run_id == target_run.id,
            target.quality_status == "eligible",
            source.preprocessing_run_id == source_run.id,
            source.quality_status == "eligible",
        )
        .subquery()
    )
    pair_count, distinct_targets, distinct_sources = db.execute(select(
        func.count(), func.count(func.distinct(pairs.c.target_id)),
        func.count(func.distinct(pairs.c.source_id)),
    )).one()
    if (pair_count, distinct_targets, distinct_sources) != (target_count, target_count, source_count):
        raise ValueError(
            "Exact vector reuse rejected: not every target chunk has one unambiguous source vector "
            "with identical film identity, language, section title, and text."
        )

    configuration_hash = embedding_configuration_hash(
        model_name=model.model_name,
        model_revision=model.model_revision,
        dimension=model.dimension,
        instruction_hash=model.instruction_hash,
        document_representation=source_index.document_representation,
    )
    existing = db.scalar(select(EmbeddingIndexRun).where(
        EmbeddingIndexRun.evidence_chunk_run_id == target_run.id,
        EmbeddingIndexRun.embedding_model_id == model.id,
        EmbeddingIndexRun.configuration_hash == configuration_hash,
    ))
    if existing is not None and not (
        existing.status == "complete" and existing.chunks_completed == target_count
    ):
        raise ValueError("A non-complete target index already exists; inspect it before retrying.")

    return {
        "source_index_run_id": str(source_index.id),
        "source_chunk_run_id": str(source_run.id),
        "target_chunk_run_id": str(target_run.id),
        "model": model.model_name,
        "model_revision": model.model_revision,
        "dimension": model.dimension,
        "source_cache_key_verified": True,
        "source_document_cache_key": source_cache_key,
        "exact_document_pairs": pair_count,
        "target_eligible_chunks": target_count,
        "existing_target_index_run_id": str(existing.id) if existing else None,
        "ready_to_apply": True,
    }


def create_exact_reuse_index(
    db: Session,
    *,
    source_index_id: UUID,
    target_chunk_run_id: UUID,
) -> EmbeddingIndexRun:
    """Create a versioned target index via one PostgreSQL INSERT..SELECT transaction."""
    plan = plan_exact_embedding_reuse(
        db, source_index_id=source_index_id, target_chunk_run_id=target_chunk_run_id,
    )
    if plan["existing_target_index_run_id"]:
        return db.get(EmbeddingIndexRun, UUID(plan["existing_target_index_run_id"]))

    source_index = db.get(EmbeddingIndexRun, source_index_id)
    source_run = db.get(EvidenceChunkRun, source_index.evidence_chunk_run_id)
    target_run = db.get(EvidenceChunkRun, target_chunk_run_id)
    model = db.get(EmbeddingModel, source_index.embedding_model_id)
    configuration_hash = embedding_configuration_hash(
        model_name=model.model_name,
        model_revision=model.model_revision,
        dimension=model.dimension,
        instruction_hash=model.instruction_hash,
        document_representation=source_index.document_representation,
    )
    index = EmbeddingIndexRun(
        evidence_chunk_run_id=target_run.id,
        embedding_model_id=model.id,
        document_representation=source_index.document_representation,
        configuration={
            "reuse_method": "exact-document-input-match-v1",
            "source_index_run_id": str(source_index.id),
            "source_document_cache_key": plan["source_document_cache_key"],
        },
        configuration_hash=configuration_hash,
        status="running",
        chunks_requested=plan["target_eligible_chunks"],
    )
    db.add(index)
    db.flush()

    target = aliased(EvidenceChunk)
    source = aliased(EvidenceChunk)
    source_vector = aliased(EvidenceEmbedding)
    exact_inputs = and_(
        target.content_hash == source.content_hash,
        target.content == source.content,
        target.section_title == source.section_title,
        target.subject_entity_id == source.subject_entity_id,
        target.language_code == source.language_code,
    )
    source_rows = (
        select(
            func.gen_random_uuid(), literal(index.id), target.id,
            target.content_hash, source_vector.embedding,
        )
        .select_from(target)
        .join(source, exact_inputs)
        .join(source_vector, and_(
            source_vector.evidence_chunk_id == source.id,
            source_vector.index_run_id == source_index.id,
        ))
        .where(
            target.preprocessing_run_id == target_run.id,
            target.quality_status == "eligible",
            source.preprocessing_run_id == source_run.id,
            source.quality_status == "eligible",
        )
    )
    db.execute(insert(EvidenceEmbedding).from_select(
        ["id", "index_run_id", "evidence_chunk_id", "content_hash", "embedding"], source_rows,
    ))
    inserted_count = db.scalar(select(func.count()).select_from(EvidenceEmbedding).where(
        EvidenceEmbedding.index_run_id == index.id,
    )) or 0
    if inserted_count != plan["target_eligible_chunks"]:
        db.rollback()
        raise RuntimeError("Inserted vector row count differs from the verified exact-match plan; transaction rolled back.")
    index.chunks_completed = inserted_count
    index.status = "complete"
    index.completed_at = datetime.now(timezone.utc)
    db.commit()
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebind exact matching local vectors to a recovered chunk run.")
    parser.add_argument("--source-index", required=True, type=UUID)
    parser.add_argument("--target-chunk-run", required=True, type=UUID)
    parser.add_argument("--apply", action="store_true", help="Persist a new index run; default is read-only preflight.")
    args = parser.parse_args()
    with SessionLocal() as db:
        report = plan_exact_embedding_reuse(
            db, source_index_id=args.source_index, target_chunk_run_id=args.target_chunk_run,
        )
        if args.apply:
            run = create_exact_reuse_index(
                db, source_index_id=args.source_index, target_chunk_run_id=args.target_chunk_run,
            )
            report["target_index_run_id"] = str(run.id)
            report["target_index_status"] = run.status
            report["vectors_completed"] = run.chunks_completed
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
