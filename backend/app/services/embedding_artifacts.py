"""Pure identity rules for local embedding artifacts."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable


DOCUMENT_REPRESENTATION = "film-section-evidence-v1"
STORAGE_DIMENSION = 1024


def embedding_configuration_hash(
    *,
    model_name: str,
    model_revision: str,
    dimension: int,
    instruction_hash: str,
    document_representation: str = DOCUMENT_REPRESENTATION,
) -> str:
    payload = {
        "model_name": model_name,
        "model_revision": model_revision,
        "dimension": dimension,
        "instruction_hash": instruction_hash,
        "document_representation": document_representation,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def document_cache_key(
    *,
    provider: str,
    model_name: str,
    dimensions: int,
    chunk_run_id: str,
    chunker_version: str,
    contents: Iterable[str],
    representation: str = DOCUMENT_REPRESENTATION,
) -> str:
    payload = {
        "provider": provider,
        "model": model_name,
        "dimensions": dimensions,
        "chunk_run_id": chunk_run_id,
        "chunker_version": chunker_version,
        "representation": representation,
        "content_hashes": [hashlib.sha256(content.encode("utf-8")).hexdigest() for content in contents],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
