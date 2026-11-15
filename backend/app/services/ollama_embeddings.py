"""Narrow local adapter for Ollama embedding models.

This adapter deliberately returns vectors only.  It has no access to CineGraph
facts and cannot publish a relationship or an answer.  Long-running index jobs
use it outside the API process.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
from urllib.parse import urlsplit

import httpx


QWEN_FILM_RETRIEVAL_INSTRUCTION = (
    "Given a film research question, retrieve the most relevant source-backed "
    "passage. Prefer direct evidence over thematic association."
)

MANIFEST_REVISION_PREFIX = "ollama-manifest-sha256:"


def local_model_digest(base_url: str, model: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme != "http" or parts.hostname not in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}:
        raise ValueError("Model digest verification requires a local Ollama endpoint.")
    response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=10.0)
    response.raise_for_status()
    matches = [item for item in response.json().get("models", []) if item.get("name") == model]
    digest = matches[0].get("digest") if len(matches) == 1 else None
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("The requested Ollama model must resolve to one SHA-256 digest.")
    return digest


@dataclass(frozen=True)
class OllamaEmbeddingProfile:
    """Explicit model/input contract; model selection remains versioned."""

    model: str = "qwen3-embedding:0.6b"
    dimensions: int = 1024
    query_instruction: str = QWEN_FILM_RETRIEVAL_INSTRUCTION
    context_window: int = 32_000
    expected_model_digest: str | None = None

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
        if profile.expected_model_digest and local_model_digest(self._base_url, profile.model) != profile.expected_model_digest:
            raise ValueError("The local embedding model no longer matches the indexed model revision.")
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
