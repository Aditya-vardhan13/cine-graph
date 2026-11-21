"""Build a local, rights-gated writer-catalog embedding index explicitly."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import ReferenceCollectionMembership
from app.services.current_narrative_passages import current_passage_rows
from app.services.disk_headroom import require_free_space
from app.services.embedding_evaluation import _cached_ollama_document_embeddings, _document_cache_key
from app.services.embedding_index import _candidate_run, _ordered_chunks_and_contents, import_embedding_cache, index_status
from app.services.evidence_preprocessing import CHUNKER_VERSION, ChunkConfiguration, _current_passages_with_snapshots, build_evidence_chunks
from app.services.narrative_use_decisions import latest_decisions
from app.services.ollama_embeddings import MANIFEST_REVISION_PREFIX, OllamaEmbeddingClient, OllamaEmbeddingProfile, local_model_digest
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.source_rights_policy import can_use_narrative_semantically


def verify_writer_sources(db: Session, collection_code: str) -> int:
    """Fail closed if any included film lacks an intact, approved source."""
    entity_ids = set(db.scalars(select(ReferenceCollectionMembership.entity_id).where(
        ReferenceCollectionMembership.collection_code == collection_code,
        ReferenceCollectionMembership.status == "included",
    )))
    if not entity_ids:
        raise ValueError("The writer collection has no included films.")
    rows = current_passage_rows(db, entity_ids)
    decisions = latest_decisions(db, {snapshot.id for _, snapshot in rows})
    checked: dict = {}
    eligible_entities = set()
    for passage, snapshot in rows:
        if snapshot.id not in checked:
            decision = decisions.get(snapshot.id)
            approved = can_use_narrative_semantically(
                decision=decision.decision if decision else None,
                basis_url=decision.decision_basis_url if decision else None,
                notes=decision.decision_notes if decision else None,
                license_name=snapshot.license, attribution_url=snapshot.attribution_url,
            )
            if approved and verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified":
                raise ValueError(f"Approved snapshot {snapshot.id} failed integrity verification.")
            checked[snapshot.id] = approved and snapshot.fetch_status == "success"
        if checked[snapshot.id]:
            if hashlib.sha256(passage.content.encode("utf-8")).hexdigest() != passage.content_hash:
                raise ValueError(f"Approved passage {passage.id} failed content integrity verification.")
            eligible_entities.add(passage.subject_entity_id)
    if entity_ids - eligible_entities:
        raise ValueError(f"{len(entity_ids - eligible_entities)} included films lack an intact approved narrative source.")
    return len(entity_ids)


def writer_passage_fingerprints(rows) -> dict[UUID, tuple]:
    """Bind embeddings and citation context to exact current passage fields."""
    return {p.id: (s.id, p.subject_entity_id, p.content_hash, p.section_locator, p.section_title,
                   p.ordinal, p.extraction_version, json.dumps(p.citation_positions or [], sort_keys=True))
            for p, s in rows}


def verify_writer_inputs_unchanged(db: Session, collection_code: str,
                                   expected_entities: set[UUID], expected_passages: dict[UUID, tuple]) -> None:
    """Reject stale work if the collection or current sources changed during embedding."""
    db.expire_all()
    entities = set(db.scalars(select(ReferenceCollectionMembership.entity_id).where(
        ReferenceCollectionMembership.collection_code == collection_code,
        ReferenceCollectionMembership.status == "included",
    )))
    if entities != expected_entities:
        raise ValueError("Writer collection membership changed during indexing; rerun the job.")
    passages = writer_passage_fingerprints(current_passage_rows(db, entities))
    if passages != expected_passages:
        raise ValueError("Current writer passages changed during indexing; rerun the job.")
    verify_writer_sources(db, collection_code)


def index_writer_catalog(db: Session, *, collection_code: str, cache_dir: Path,
                         ollama_url: str, batch_size: int = 8,
                         source_parser_version: str | None = None,
                         extraction_version: str | None = None,
                         chunk_config: ChunkConfiguration | None = None,
                         profile: OllamaEmbeddingProfile | None = None) -> dict:
    settings = get_settings()
    if collection_code != settings.writer_catalog_collection_code or collection_code == settings.research_collection_code:
        raise ValueError("Only the distinct configured writer catalog may be indexed by this job.")
    if not 1 <= batch_size <= 24:
        raise ValueError("Batch size must be between 1 and 24.")
    films = verify_writer_sources(db, collection_code)
    included = set(db.scalars(select(ReferenceCollectionMembership.entity_id).where(
        ReferenceCollectionMembership.collection_code == collection_code,
        ReferenceCollectionMembership.status == "included",
    )))
    current_passages = writer_passage_fingerprints(current_passage_rows(db, included))
    current_ids = set(current_passages)
    current_per_snapshot = source_parser_version is None and extraction_version is None
    selected = [(passage, snapshot) for passage, snapshot in _current_passages_with_snapshots(
        db, collection_code=collection_code, language_code="en",
    ) if (source_parser_version is None or snapshot.parser_version == source_parser_version)
         and (extraction_version is None or passage.extraction_version == extraction_version)
         and (not current_per_snapshot or passage.id in current_ids)]
    if any(passage.id not in current_ids for passage, _ in selected):
        raise ValueError("Selected passages include a non-current extraction; choose the current extraction version.")
    profile = profile or OllamaEmbeddingProfile()
    digest = local_model_digest(ollama_url, profile.model)
    if profile.expected_model_digest is not None and digest != profile.expected_model_digest:
        raise ValueError("The local embedding model does not match the requested pinned digest.")
    if profile.dimensions != 1024:
        raise ValueError("The writer catalog index requires 1,024-dimensional vectors.")
    cache_dir = cache_dir / digest
    cache_dir.mkdir(parents=True, exist_ok=True)
    minimum_free_bytes = 6 * 1024**3
    require_free_space(cache_dir, minimum_free_bytes)
    report = build_evidence_chunks(db, collection_code=collection_code, config=replace(
        chunk_config or ChunkConfiguration(),
        source_parser_version=source_parser_version, extraction_version=extraction_version,
        current_extractions_per_snapshot=current_per_snapshot,
    ))
    run = _candidate_run(db, collection_code=collection_code, chunker_version=CHUNKER_VERSION,
                         run_id=UUID(report["run_id"]))
    chunks, contents = _ordered_chunks_and_contents(db, run)
    if not chunks or len({chunk.subject_entity_id for chunk in chunks}) != films:
        raise ValueError("Every included film needs at least one eligible approved chunk in the selected run.")
    key = _document_cache_key(profile=profile, run=run, contents=contents)
    cache_path = cache_dir / f"{profile.model.replace('/', '--').replace(':', '--')}-{key}.npy"
    vectors, reused = _cached_ollama_document_embeddings(
        OllamaEmbeddingClient(base_url=ollama_url), contents, profile=profile,
        run=run, batch_size=batch_size, cache_dir=cache_dir, minimum_free_bytes=minimum_free_bytes,
    )
    for offset in range(0, len(vectors), 256):
        batch = vectors[offset:offset + 256]
        if not np.isfinite(batch).all() or np.any(np.linalg.norm(batch, axis=1) == 0):
            raise ValueError("Embedding cache contains a non-finite or zero vector.")
    del vectors
    if local_model_digest(ollama_url, profile.model) != digest:
        raise ValueError("The Ollama model tag changed during indexing; no vectors were imported.")
    verify_writer_inputs_unchanged(db, collection_code, included, current_passages)
    index = import_embedding_cache(db, cache_path=cache_path, collection_code=collection_code,
                                   chunker_version=CHUNKER_VERSION, model_name=profile.model,
                                   model_revision=f"{MANIFEST_REVISION_PREFIX}{digest}", dimension=profile.dimensions,
                                   query_instruction=profile.query_instruction, chunk_run_id=run.id)
    return {"films": films, "chunk_report": report, "model_digest": digest,
            "cache_reused": reused, **index_status(db, str(index.id))}


def recovery_profile(model: str, digest: str) -> OllamaEmbeddingProfile:
    """Construct an explicit >=4B candidate, without changing legacy callers."""
    if model not in {"qwen3-embedding:4b", "qwen3-embedding:8b"}:
        raise ValueError("Recovery indexing requires an explicitly selected Qwen 4B or 8B embedding model.")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Recovery indexing requires an exact Ollama SHA-256 model digest.")
    return OllamaEmbeddingProfile(model=model, expected_model_digest=digest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Explicitly build and import writer catalog vectors.")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/writer-catalog/embedding-cache"))
    parser.add_argument("--ollama-url", default=get_settings().ollama_base_url)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--source-parser-version")
    parser.add_argument("--extraction-version")
    parser.add_argument("--model", required=True, choices=("qwen3-embedding:4b", "qwen3-embedding:8b"))
    parser.add_argument("--model-digest", required=True, help="Exact local Ollama manifest SHA-256")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required to write writer catalog chunks and vectors")
    with SessionLocal() as db:
        result = index_writer_catalog(db, collection_code=get_settings().writer_catalog_collection_code,
                                      cache_dir=args.cache_dir, ollama_url=args.ollama_url,
                                      batch_size=args.batch_size, source_parser_version=args.source_parser_version,
                                      extraction_version=args.extraction_version,
                                      profile=recovery_profile(args.model, args.model_digest))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
