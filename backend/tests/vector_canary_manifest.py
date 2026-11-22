"""Persist a local canary's exact vector-row provenance before schema teardown."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

import numpy as np

from app.models import EvidenceChunkRun, SourceSnapshot
from app.services.corpus_build_manifest import canonical_digest
from app.services.embedding_evaluation import _document_cache_key
from app.services.embedding_index import _ordered_chunks_and_contents


def save_canary_vector_manifest(db, *, run_id, profile, model_digest, cache_dir: Path,
                                output: Path, corpus_fingerprint: str) -> dict:
    """Bind one completed cache to the actual run, contents and source snapshots."""
    run = db.get(EvidenceChunkRun, UUID(str(run_id)))
    if run is None:
        raise ValueError("Missing canary preprocessing run")
    chunks, contents = _ordered_chunks_and_contents(db, run)
    if not chunks:
        raise ValueError("Canary run has no eligible chunks")
    cache_key = _document_cache_key(profile=profile, run=run, contents=contents)
    cache = cache_dir / model_digest / f"{profile.model.replace('/', '--').replace(':', '--')}-{cache_key}.npy"
    vectors = np.load(cache, mmap_mode="r", allow_pickle=False)
    if vectors.shape != (len(chunks), profile.dimensions) or vectors.dtype != np.float32:
        raise ValueError("Canary vector matrix does not match its recorded inputs")
    sources = {chunk.source_snapshot_id: db.get(SourceSnapshot, chunk.source_snapshot_id) for chunk in chunks}
    if any(source is None for source in sources.values()):
        raise ValueError("Missing source snapshot for canary vector")
    with cache.open("rb") as handle:
        matrix_sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    manifest = {"schema": "cinegraph.canary-vector-mapping/v1", "corpus_fingerprint": corpus_fingerprint,
        "preprocessing_run_id": str(run.id), "cache_key": cache_key, "model": profile.model,
        "model_digest": model_digest, "dimension": profile.dimensions, "dtype": str(vectors.dtype),
        "matrix_path": str(cache), "matrix_sha256": matrix_sha256,
        "rows": [{"row": i, "chunk_id": str(c.id), "passage_id": str(c.narrative_passage_id),
            "entity_id": str(c.subject_entity_id), "snapshot_id": str(c.source_snapshot_id),
            "source_sha256": sources[c.source_snapshot_id].content_hash,
            "chunk_sha256": c.content_hash, "section_locator": c.section_locator,
            "chunk_ordinal": c.chunk_ordinal, "citation_positions": c.citation_positions,
            "document_input_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
            for i, (c, content) in enumerate(zip(chunks, contents, strict=True))]}
    manifest["fingerprint"] = canonical_digest(manifest)
    with output.open("x") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest
