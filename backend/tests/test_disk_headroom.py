"""Exercise the disk guard against real filesystem free-space readings."""
import shutil

import pytest
from uuid import uuid4

from app.services.disk_headroom import require_free_space
from app.models import EvidenceChunkRun
from app.services.embedding_evaluation import _cached_ollama_document_embeddings
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile


def test_free_space_guard_uses_actual_filesystem(tmp_path):
    require_free_space(tmp_path, 0)
    with pytest.raises(RuntimeError, match="Insufficient free space"):
        require_free_space(tmp_path, shutil.disk_usage(tmp_path).total + 1)
    with pytest.raises(ValueError, match="cannot be negative"):
        require_free_space(tmp_path, -1)


def test_embedding_guard_stops_before_creating_cache_or_calling_model(tmp_path):
    run = EvidenceChunkRun(id=uuid4(), collection_code="test", chunker_version="test",
                           language_code="en", configuration_hash="0" * 64, configuration={})
    with pytest.raises(RuntimeError, match="Insufficient free space"):
        _cached_ollama_document_embeddings(OllamaEmbeddingClient(), ["A retained passage."],
            profile=OllamaEmbeddingProfile(), run=run, batch_size=1, cache_dir=tmp_path,
            minimum_free_bytes=shutil.disk_usage(tmp_path).total + 1)
    assert not list(tmp_path.iterdir())
