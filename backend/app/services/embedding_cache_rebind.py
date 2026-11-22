"""Rebind a retained local vector matrix to an exact new evidence-chunk run.

This prepares an inactive cache only. It does not import or activate an index.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
from sqlalchemy.orm import Session

from app.models import EvidenceChunkRun, SourceSnapshot
from app.services.corpus_build_manifest import canonical_digest
from app.services.current_narrative_passages import current_passage_rows
from app.services.embedding_artifacts import document_cache_key
from app.services.embedding_index import _ordered_chunks_and_contents
from app.services.evidence_preprocessing import CHUNKER_VERSION, ChunkConfiguration, chunk_passage
from app.services.snapshot_integrity import verify_snapshot_file


def rebind_exact_cache(db: Session, *, run: EvidenceChunkRun, mapping: dict,
                       matrix_path: Path, output_dir: Path, expected_model_digest: str) -> Path:
    """Reject any ambiguous, stale, or changed document before writing a cache."""
    if canonical_digest({k: v for k, v in mapping.items() if k != "fingerprint"}) != mapping.get("fingerprint"):
        raise ValueError("mapping_fingerprint_mismatch")
    if (run.status != "complete" or mapping.get("schema") != "cinegraph.canary-vector-mapping/v1"
            or mapping.get("model") != "qwen3-embedding:4b" or mapping.get("dimension") != 1024
            or mapping.get("dtype") != "float32" or not re.fullmatch(r"[0-9a-f]{64}", expected_model_digest)
            or mapping.get("model_digest") != expected_model_digest):
        raise ValueError("unsupported_run_or_model")
    with matrix_path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != mapping["matrix_sha256"]:
            raise ValueError("matrix_integrity_failed")
    matrix = np.load(matrix_path, mmap_mode="r", allow_pickle=False)
    rows = mapping["rows"]
    if matrix.dtype != np.float32 or matrix.shape != (len(rows), 1024) or not np.isfinite(matrix).all():
        raise ValueError("matrix_shape_or_values_invalid")
    if np.any(np.linalg.norm(matrix, axis=1) == 0):
        raise ValueError("zero_vector")
    def key(row):
        return (row["passage_id"], row["entity_id"], row["snapshot_id"],
                row["chunk_ordinal"], row["chunk_sha256"], row["section_locator"])
    old = {}
    for index, row in enumerate(rows):
        if row["row"] != index or key(row) in old:
            raise ValueError("ambiguous_source_mapping")
        old[key(row)] = row
    chunks, contents = _ordered_chunks_and_contents(db, run)
    if not chunks or len(chunks) != len(rows):
        raise ValueError("eligible_chunk_count_mismatch")
    if run.chunker_version != CHUNKER_VERSION:
        raise ValueError("unsupported_chunker_version")
    configuration_hash = hashlib.sha256(json.dumps(run.configuration, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    if configuration_hash != run.configuration_hash:
        raise ValueError("chunker_configuration_mismatch")
    config = ChunkConfiguration(**{key: value for key, value in run.configuration.items()
                                   if key not in {"input_manifest_hash", "rights_manifest_hash"}})
    current_passages = {passage.id: (passage, snapshot.id) for passage, snapshot in current_passage_rows(
        db, {chunk.subject_entity_id for chunk in chunks})}
    if any(chunk.narrative_passage_id not in current_passages or
           current_passages[chunk.narrative_passage_id][1] != chunk.source_snapshot_id for chunk in chunks):
        raise ValueError("non_current_source_or_extraction")
    source_indices = []
    verified_snapshots = set()
    prepared = {}
    for chunk, content in zip(chunks, contents, strict=True):
        identity = (str(chunk.narrative_passage_id), str(chunk.subject_entity_id),
                    str(chunk.source_snapshot_id), chunk.chunk_ordinal, chunk.content_hash, chunk.section_locator)
        row = old.get(identity)
        snapshot = db.get(SourceSnapshot, chunk.source_snapshot_id)
        passage = current_passages[chunk.narrative_passage_id][0]
        if (passage.subject_entity_id != chunk.subject_entity_id or passage.language_code != chunk.language_code
                or hashlib.sha256(passage.content.encode("utf-8")).hexdigest() != passage.content_hash):
            raise ValueError("passage_integrity_failed")
        if passage.id not in prepared:
            prepared[passage.id] = chunk_passage(passage.content, language_code=chunk.language_code, config=config)
        candidates = prepared[passage.id]
        if (row is None or snapshot is None or snapshot.content_hash != row["source_sha256"]
                or snapshot.fetch_status != "success"
                or chunk.chunk_ordinal < 0 or chunk.chunk_ordinal >= len(candidates)
                or candidates[chunk.chunk_ordinal].content_hash != chunk.content_hash
                or hashlib.sha256(chunk.content.encode("utf-8")).hexdigest() != chunk.content_hash
                or hashlib.sha256(content.encode("utf-8")).hexdigest() != row["document_input_sha256"]):
            raise ValueError("source_or_document_input_mismatch")
        if snapshot.id not in verified_snapshots:
            if verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified":
                raise ValueError("snapshot_integrity_failed")
            verified_snapshots.add(snapshot.id)
        source_indices.append(row["row"])
    if len(set(source_indices)) != len(rows):
        raise ValueError("ambiguous_target_mapping")
    key_digest = document_cache_key(provider="ollama", model_name=mapping["model"], dimensions=1024,
        chunk_run_id=str(run.id), chunker_version=run.chunker_version, contents=contents)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"qwen3-embedding--4b-{key_digest}.npy"
    # Exclusive creation ensures a failed or repeated attempt cannot overwrite a cache.
    with output.open("xb") as handle:
        np.save(handle, np.asarray(matrix[source_indices], dtype=np.float32), allow_pickle=False)
    return output
