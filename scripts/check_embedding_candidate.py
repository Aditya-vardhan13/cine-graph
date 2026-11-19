"""Explicit local model contract check; never builds or activates an index."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

from app.services.ollama_embeddings import (
    OllamaEmbeddingClient, OllamaEmbeddingProfile, local_model_digest,
)


def vector_statistics(vectors, expected_dimension):
    if not vectors or any(len(v) != expected_dimension for v in vectors):
        raise ValueError("unexpected_vector_shape")
    norms = []
    for vector in vectors:
        if not all(math.isfinite(x) for x in vector):
            raise ValueError("nonfinite_vector")
        norm = math.sqrt(sum(x*x for x in vector))
        if norm <= 0:
            raise ValueError("zero_vector")
        norms.append(norm)
    return norms


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", choices=["qwen3-embedding:4b", "qwen3-embedding:8b",
                                     "qwen3-embedding:4b-q8_0"], required=True)
    p.add_argument("--expected-digest", required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:11434")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("output already exists")
    actual = local_model_digest(args.base_url, args.model)
    if actual != args.expected_digest:
        raise ValueError("candidate_digest_mismatch")
    profile = OllamaEmbeddingProfile(model=args.model, dimensions=1024,
                                    context_window=40960, expected_model_digest=actual)
    # Original diagnostic prose, not corpus evidence or relevance labels.
    documents = [
        "A prisoner risks punishment to give his friends a moment of freedom.",
        "A jury changes its verdict after questioning the reliability of testimony.",
        "The production used miniature sets and practical lighting.",
    ]
    client = OllamaEmbeddingClient(base_url=args.base_url, timeout_seconds=120)
    start = time.monotonic()
    vectors = client.embed(documents, profile=profile)
    document_seconds = time.monotonic() - start
    norms = vector_statistics(vectors, 1024)
    start = time.monotonic()
    query = client.embed([profile.query_input("How does a character protect others at personal cost?")],
                         profile=profile)
    query_seconds = time.monotonic() - start
    query_norm = vector_statistics(query, 1024)[0]
    if local_model_digest(args.base_url, args.model) != actual:
        raise ValueError("candidate_changed_during_check")
    result = {
        "schema": "cinegraph.embedding-candidate-contract/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model, "digest": actual, "dimension": 1024,
        "query_instruction": profile.query_instruction,
        "context_window_declared": profile.context_window,
        "long_input_behavior_tested": False,
        "document_hashes": [hashlib.sha256(s.encode()).hexdigest() for s in documents],
        "document_norms": norms, "query_norm": query_norm,
        "document_batch_seconds": document_seconds, "query_seconds": query_seconds,
        "quality_claim": None, "index_built": False, "serving_changed": False,
    }
    with args.output.open("x") as handle:
        json.dump(result, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
