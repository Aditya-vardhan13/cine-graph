"""Read-only evidence/vector integrity check; never activates an index."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import EmbeddingIndexRun, EmbeddingModel, EvidenceChunk, EvidenceChunkRun, EvidenceEmbedding, NarrativePassage, SourceSnapshot
from app.services.current_narrative_passages import current_passage_rows
from app.services.embedding_artifacts import DOCUMENT_REPRESENTATION, document_cache_key, embedding_configuration_hash
from app.services.embedding_index import _ordered_chunks_and_contents, instruction_hash
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.ollama_embeddings import MANIFEST_REVISION_PREFIX


def audit_index(db: Session, index_id: UUID) -> dict:
    """Check exact vector membership and source lineage against current decisions.

    This checks integrity, not relevance, legal sufficiency, or whether vectors
    actually came from the named model. Run under a read-only snapshot.
    """
    index = db.get(EmbeddingIndexRun, index_id)
    if index is None:
        raise ValueError("index_not_found")
    run = db.get(EvidenceChunkRun, index.evidence_chunk_run_id)
    model = db.get(EmbeddingModel, index.embedding_model_id)
    if run is None or model is None:
        raise ValueError("index_lineage_missing")
    chunks, contents = _ordered_chunks_and_contents(db, run)
    expected = {chunk.id for chunk in chunks}
    current = {p.id for p, _ in current_passage_rows(db, {c.subject_entity_id for c in chunks})}
    errors: dict[str, int] = {}

    def fail(reason: str) -> None:
        errors[reason] = errors.get(reason, 0) + 1

    if not expected:
        fail("no_currently_approved_chunks")
    if index.status != "complete" or run.status != "complete":
        fail("run_not_complete")
    if (index.chunks_requested != len(expected) or index.chunks_completed != len(expected)
            or index.chunks_failed != 0):
        fail("counter_mismatch")
    if index.document_representation != DOCUMENT_REPRESENTATION or model.dimension != 1024:
        fail("unsupported_embedding_contract")
    if (model.provider != "ollama" or not re.fullmatch(
            re.escape(MANIFEST_REVISION_PREFIX) + r"[0-9a-f]{64}", model.model_revision)):
        fail("unpinned_model_contract")
    if model.instruction_hash != instruction_hash(model.query_instruction):
        fail("instruction_hash_mismatch")
    if index.configuration_hash != embedding_configuration_hash(
        model_name=model.model_name, model_revision=model.model_revision, dimension=model.dimension,
        instruction_hash=model.instruction_hash, document_representation=index.document_representation,
    ):
        fail("configuration_hash_mismatch")
    cache_key = document_cache_key(provider=model.provider, model_name=model.model_name,
        dimensions=model.dimension, chunk_run_id=str(run.id), chunker_version=run.chunker_version,
        contents=contents, representation=index.document_representation)
    if (index.configuration or {}).get("cache_key") != cache_key:
        fail("document_cache_key_mismatch")
    seen = set()
    snapshots = {}
    stmt = (select(EvidenceEmbedding, EvidenceChunk, NarrativePassage, SourceSnapshot)
        .join(EvidenceChunk, EvidenceChunk.id == EvidenceEmbedding.evidence_chunk_id)
        .join(NarrativePassage, NarrativePassage.id == EvidenceChunk.narrative_passage_id)
        .join(SourceSnapshot, SourceSnapshot.id == EvidenceChunk.source_snapshot_id)
        .where(EvidenceEmbedding.index_run_id == index.id)
        .execution_options(yield_per=256))
    for vector, chunk, passage, snapshot in db.execute(stmt):
        seen.add(chunk.id)
        if chunk.id not in expected:
            fail("unexpected_or_unapproved_vector")
        if (chunk.preprocessing_run_id != run.id or chunk.subject_entity_id != passage.subject_entity_id
            or chunk.source_snapshot_id != passage.source_snapshot_id or chunk.language_code != passage.language_code):
            fail("chunk_source_lineage_mismatch")
        if (chunk.id in expected and passage.id not in current) or snapshot.fetch_status != "success":
            fail("source_not_current")
        if (hashlib.sha256(chunk.content.encode()).hexdigest() != chunk.content_hash
            or vector.content_hash != chunk.content_hash):
            fail("chunk_or_vector_hash_mismatch")
        if hashlib.sha256(passage.content.encode()).hexdigest() != passage.content_hash:
            fail("passage_hash_mismatch")
        values = vector.embedding
        if len(values) != model.dimension or any(not math.isfinite(float(v)) for v in values) or not any(values):
            fail("invalid_vector")
        snapshots[snapshot.id] = snapshot
    missing = expected - seen
    if missing:
        errors["missing_vectors"] = len(missing)
    for snapshot in snapshots.values():
        if verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified":
            fail("snapshot_integrity_failed")
    return {"index_id": str(index.id), "collection": run.collection_code,
        "model": model.model_name, "model_revision": model.model_revision,
        "expected_chunks": len(expected), "vector_rows": len(seen),
        "snapshots_checked": len(snapshots), "errors": errors, "integrity_pass": not errors,
        "limitations": "Integrity only; does not verify model inference, retrieval quality, or permission for public use."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index_id", type=UUID)
    args = parser.parse_args()
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        result = audit_index(db, args.index_id)
    print(json.dumps(result, indent=2))
    if not result["integrity_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
