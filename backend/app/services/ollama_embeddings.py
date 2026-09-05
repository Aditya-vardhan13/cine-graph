"""Narrow local adapter for Ollama embedding models.

This adapter deliberately returns vectors only.  It has no access to CineGraph
facts and cannot publish a relationship or an answer.  Long-running index jobs
use it outside the API process.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import httpx


QWEN_FILM_RETRIEVAL_INSTRUCTION = (
    "Given a film research question, retrieve the most relevant source-backed "
    "passage. Prefer direct evidence over thematic association."
)


@dataclass(frozen=True)
class OllamaEmbeddingProfile:
    """Explicit model/input contract; model selection remains versioned."""

    model: str = "qwen3-embedding:0.6b"
    dimensions: int = 1024
    query_instruction: str = QWEN_FILM_RETRIEVAL_INSTRUCTION
    context_window: int = 32_000

    def query_input(self, question: str) -> str:
        return f"Instruct: {self.query_instruction}\nQuery: {question.strip()}"


class OllamaEmbeddingClient:
    """HTTP client for the local `/api/embed` endpoint only."""

    def __init__(self, *, base_url: str = "http://127.0.0.1:11434", timeout_seconds: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def embed(self, values: Iterable[str], *, profile: OllamaEmbeddingProfile) -> list[list[float]]:
        inputs = [value for value in values if value.strip()]
        if not inputs:
            return []
        response = httpx.post(
            f"{self._base_url}/api/embed",
            json={
                "model": profile.model,
                "input": inputs,
                "dimensions": profile.dimensions,
                # Failing on an over-limit input is mandatory.  Truncation is
                # data loss and must be addressed by a new chunk-run policy.
                "truncate": False,
                "keep_alive": "10m",
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
            raise RuntimeError("Ollama returned an embedding count that does not match the requested inputs.")
        vectors = [[float(component) for component in vector] for vector in embeddings]
        if any(len(vector) != profile.dimensions for vector in vectors):
            actual = sorted({len(vector) for vector in vectors})
            raise RuntimeError(f"Ollama returned dimensions {actual}, expected {profile.dimensions}.")
        return vectors
