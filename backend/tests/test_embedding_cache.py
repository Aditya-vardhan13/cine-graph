import json

import numpy as np

from app.services.embedding_evaluation import _cached_ollama_document_embeddings, _document_cache_key
from app.services.ollama_embeddings import OllamaEmbeddingProfile


class _Run:
    id = "test-run"
    chunker_version = "test-chunker"


def test_document_cache_key_changes_when_retrieval_representation_changes() -> None:
    profile = OllamaEmbeddingProfile()

    first = _document_cache_key(profile=profile, run=_Run(), contents=["Film: A\nEvidence: one"])
    second = _document_cache_key(profile=profile, run=_Run(), contents=["Film: A\nEvidence: two"])

    assert first != second


class _RecordingEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, values: list[str], *, profile: OllamaEmbeddingProfile) -> list[list[float]]:
        batch = list(values)
        self.calls.append(batch)
        return [[float(len(value)), float(index)] for index, value in enumerate(batch)]


def test_document_cache_resumes_after_completed_batch(tmp_path) -> None:
    contents = ["one", "two", "three"]
    profile = OllamaEmbeddingProfile(model="test/model", dimensions=2)
    key = _document_cache_key(profile=profile, run=_Run(), contents=contents)
    vector_path = tmp_path / f"test--model-{key}.npy"
    partial_path = vector_path.with_suffix(".partial.npy")
    progress_path = vector_path.with_suffix(".progress.json")
    partial = np.lib.format.open_memmap(partial_path, mode="w+", dtype=np.float32, shape=(3, 2))
    partial[0] = [3.0, 99.0]
    partial.flush()
    del partial
    progress_path.write_text(json.dumps({"cache_key": key, "next_offset": 1}), encoding="utf-8")
    client = _RecordingEmbeddingClient()

    matrix, reused = _cached_ollama_document_embeddings(
        client,
        contents,
        profile=profile,
        run=_Run(),
        batch_size=1,
        cache_dir=tmp_path,
    )

    assert reused is False
    assert client.calls == [["two"], ["three"]]
    assert matrix.tolist() == [[3.0, 99.0], [3.0, 0.0], [5.0, 0.0]]
    assert vector_path.exists()
    assert not partial_path.exists()
    assert not progress_path.exists()
