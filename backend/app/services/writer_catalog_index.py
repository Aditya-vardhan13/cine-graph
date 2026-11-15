"""Build a local, rights-gated writer-catalog embedding index explicitly."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import ReferenceCollectionMembership
from app.services.current_narrative_passages import current_passage_rows
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
            eligible_entities.add(passage.subject_entity_id)
    if entity_ids - eligible_entities:
        raise ValueError(f"{len(entity_ids - eligible_entities)} included films lack an intact approved narrative source.")
    return len(entity_ids)


def index_writer_catalog(db: Session, *, collection_code: str, cache_dir: Path,
                         ollama_url: str, batch_size: int = 8,
                         source_parser_version: str | None = None,
                         extraction_version: str | None = None) -> dict:
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
    current_ids = {passage.id for passage, _ in current_passage_rows(db, included)}
    current_per_snapshot = source_parser_version is None and extraction_version is None
    selected = [(passage, snapshot) for passage, snapshot in _current_passages_with_snapshots(
        db, collection_code=collection_code, language_code="en",
    ) if (source_parser_version is None or snapshot.parser_version == source_parser_version)
         and (extraction_version is None or passage.extraction_version == extraction_version)
         and (not current_per_snapshot or passage.id in current_ids)]
    if any(passage.id not in current_ids for passage, _ in selected):
        raise ValueError("Selected passages include a non-current extraction; choose the current extraction version.")
    profile = OllamaEmbeddingProfile()
    digest = local_model_digest(ollama_url, profile.model)
    cache_dir = cache_dir / digest
    cache_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(cache_dir).free < 2 * 1024**3:
        raise RuntimeError("At least 2 GiB free space is required for local indexing.")
    report = build_evidence_chunks(db, collection_code=collection_code, config=ChunkConfiguration(
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
        run=run, batch_size=batch_size, cache_dir=cache_dir,
    )
    for offset in range(0, len(vectors), 256):
        batch = vectors[offset:offset + 256]
        if not np.isfinite(batch).all() or np.any(np.linalg.norm(batch, axis=1) == 0):
            raise ValueError("Embedding cache contains a non-finite or zero vector.")
    del vectors
    if local_model_digest(ollama_url, profile.model) != digest:
        raise ValueError("The Ollama model tag changed during indexing; no vectors were imported.")
    index = import_embedding_cache(db, cache_path=cache_path, collection_code=collection_code,
                                   chunker_version=CHUNKER_VERSION, model_name=profile.model,
                                   model_revision=f"{MANIFEST_REVISION_PREFIX}{digest}", dimension=profile.dimensions,
                                   query_instruction=profile.query_instruction, chunk_run_id=run.id)
    return {"films": films, "chunk_report": report, "model_digest": digest,
            "cache_reused": reused, **index_status(db, str(index.id))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Explicitly build and import writer catalog vectors.")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/writer-catalog/embedding-cache"))
    parser.add_argument("--ollama-url", default=get_settings().ollama_base_url)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--source-parser-version")
    parser.add_argument("--extraction-version")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required to write writer catalog chunks and vectors")
    with SessionLocal() as db:
        result = index_writer_catalog(db, collection_code=get_settings().writer_catalog_collection_code,
                                      cache_dir=args.cache_dir, ollama_url=args.ollama_url,
                                      batch_size=args.batch_size, source_parser_version=args.source_parser_version,
                                      extraction_version=args.extraction_version)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
