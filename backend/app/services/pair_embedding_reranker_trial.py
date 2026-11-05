"""Offline 4B embedding reranking over an existing frozen candidate union."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np

from app.db import settings
from app.services.embedding_evaluation import _cached_ollama_document_embeddings
from app.services.ollama_embeddings import (
    QWEN_FILM_RETRIEVAL_INSTRUCTION,
    OllamaEmbeddingClient,
    OllamaEmbeddingProfile,
)
from app.services.pair_relevance_eval import validate_reranking


def restrict_to_reviewed_candidates(capture: dict, packet: dict) -> dict:
    """Keep only already-reviewed candidates from a model-blind packet."""
    case_by_id = {case["case_id"]: case for case in capture.get("cases", [])}
    allowed: dict[tuple[str, str], set[str]] = {}
    for item in packet.get("items", []):
        try:
            case_id, qid, chunk_id = item["key"].split("|", 2)
        except (KeyError, ValueError) as exc:
            raise ValueError("Review packet contains an invalid candidate key.") from exc
        if case_id not in case_by_id:
            raise ValueError(f"Review packet refers to unknown case {case_id}.")
        case = case_by_id[case_id]
        if qid not in case["film_qids"]:
            raise ValueError(f"Review packet film differs for {case_id}.")
        allowed.setdefault((case_id, qid), set()).add(chunk_id)

    result = deepcopy(capture)
    for case in result["cases"]:
        for side, qid in zip(("first", "second"), case["film_qids"], strict=True):
            selected = allowed.get((case["case_id"], qid), set())
            pool = [item for item in case[f"{side}_pool"] if item["chunk_id"] in selected]
            if not pool or {item["chunk_id"] for item in pool} != selected:
                raise ValueError(f"Review packet candidates do not match the {case['case_id']} {side} pool.")
            case[f"{side}_pool"] = pool
            case[f"{side}_options"] = pool[:3]
    return result


def rank_candidate_union(
    capture: dict,
    *,
    chunks: list[dict],
    matrix: np.ndarray,
    query_vectors: list[list[float]],
) -> dict:
    """Produce a full ranking for each film side without crossing film scope."""
    cases = capture["cases"]
    if len(cases) != 50 or len(query_vectors) != 50:
        raise ValueError("A complete 50-question capture and one vector per question are required.")
    if matrix.ndim != 2 or matrix.shape[0] != len(chunks):
        raise ValueError("One document vector is required per unique candidate chunk.")
    if any(len(vector) != matrix.shape[1] for vector in query_vectors):
        raise ValueError("Query and document embedding dimensions must match.")
    index_by_id = {item["chunk_id"]: index for index, item in enumerate(chunks)}
    norm = np.linalg.norm(matrix, axis=1)
    if np.any(norm == 0):
        raise ValueError("Zero-length document embeddings cannot be ranked.")

    rankings = []
    for case_index, case in enumerate(cases):
        vector = np.asarray(query_vectors[case_index], dtype=np.float32)
        query_norm = np.linalg.norm(vector)
        if query_norm == 0:
            raise ValueError("Zero-length query embeddings cannot be ranked.")
        row = {"case_id": case["case_id"], "question": case["question"], "film_qids": case["film_qids"]}
        for side in ("first", "second"):
            pool = case[f"{side}_pool"]
            indexes = [index_by_id[item["chunk_id"]] for item in pool]
            scores = (matrix[indexes] @ vector) / (norm[indexes] * query_norm)
            order = np.argsort(-scores, kind="stable")
            row[f"{side}_ranking"] = [
                {"chunk_id": pool[int(position)]["chunk_id"],
                 "score": round(float(scores[int(position)]), 6),
                 "section_title": pool[int(position)]["section_title"]}
                for position in order
            ]
        rankings.append(row)
    result = {
        "model": "qwen3-embedding-4b-cosine-over-candidate-union",
        "instruction": QWEN_FILM_RETRIEVAL_INSTRUCTION,
        "capture": "candidates-hybrid-lexical-union.json",
        "complete": True,
        "cases": rankings,
    }
    validate_reranking(capture, result)
    return result


def rerank(
    capture: dict,
    *,
    model_name: str,
    ollama_base_url: str,
    cache_dir: Path,
    batch_size: int,
) -> dict:
    """Embed each unique captured passage once, cache locally, rank the 50 cases."""
    if batch_size < 1:
        raise ValueError("Batch size must be positive.")
    if capture.get("method") != "candidate-union" or len(capture.get("cases", [])) != 50:
        raise ValueError("A complete hybrid/lexical candidate-union capture is required.")

    titles_by_subject: dict[str, str] = {}
    chunks_by_id: dict[str, dict] = {}
    for case in capture["cases"]:
        for side, title in zip(("first", "second"), case["titles"], strict=True):
            for item in case[f"{side}_pool"]:
                previous_title = titles_by_subject.setdefault(item["subject_entity_id"], title)
                if previous_title != title:
                    raise ValueError("A candidate subject is associated with different film titles.")
                previous = chunks_by_id.setdefault(item["chunk_id"], item)
                stable = ("content", "subject_entity_id", "source_snapshot_id", "section_locator", "section_title")
                if any(previous.get(key) != item.get(key) for key in stable):
                    raise ValueError(f"Source passage changed for chunk {item['chunk_id']}.")

    chunks = [chunks_by_id[key] for key in sorted(chunks_by_id)]
    documents = [
        f"Film: {titles_by_subject[item['subject_entity_id']]}\nSection: {item['section_title']}\nEvidence: {item['content']}"
        for item in chunks
    ]
    digest = hashlib.sha256("\n".join(item["chunk_id"] for item in chunks).encode()).hexdigest()
    cache_run = SimpleNamespace(id=f"candidate-union:{digest}", chunker_version="pair-union-candidates-v1")
    profile = OllamaEmbeddingProfile(
        model=model_name, dimensions=1024,
        query_instruction=QWEN_FILM_RETRIEVAL_INSTRUCTION,
    )
    client = OllamaEmbeddingClient(base_url=ollama_base_url, timeout_seconds=300)
    started = perf_counter()
    matrix, cache_reused = _cached_ollama_document_embeddings(
        client, documents, profile=profile, run=cache_run,
        batch_size=batch_size, cache_dir=cache_dir,
    )
    document_seconds = perf_counter() - started

    query_inputs = [profile.query_input(case["question"]) for case in capture["cases"]]
    query_vectors: list[list[float]] = []
    query_started = perf_counter()
    for offset in range(0, len(query_inputs), batch_size):
        batch = query_inputs[offset:offset + batch_size]
        query_vectors.extend(client.embed(batch, profile=profile))
        print(f"[{model_name}] pair questions: {min(offset + len(batch), len(query_inputs))}/{len(query_inputs)}", flush=True)
    query_seconds = perf_counter() - query_started

    result = rank_candidate_union(capture, chunks=chunks, matrix=matrix, query_vectors=query_vectors)
    result["model"] = model_name
    result["dimension"] = profile.dimensions
    result["query_instruction"] = profile.query_instruction
    result["candidate_count"] = len(chunks)
    result["document_cache_reused"] = cache_reused
    result["document_embedding_seconds"] = round(document_seconds, 2)
    result["query_embedding_seconds"] = round(query_seconds, 2)
    result["elapsed_seconds"] = round(perf_counter() - started, 2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--model", default="qwen3-embedding:4b")
    parser.add_argument("--ollama-base-url", default=settings.ollama_base_url)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--review-packet", type=Path,
        help="Limit to candidates already in a reviewed packet for a cheap selector diagnostic.",
    )
    parser.add_argument(
        "--restricted-capture-output", type=Path,
        help="Optionally save the exact candidate subset used by the diagnostic.",
    )
    args = parser.parse_args()
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    if args.review_packet:
        packet = json.loads(args.review_packet.read_text(encoding="utf-8"))
        capture = restrict_to_reviewed_candidates(capture, packet)
        if args.restricted_capture_output:
            args.restricted_capture_output.parent.mkdir(parents=True, exist_ok=True)
            args.restricted_capture_output.write_text(json.dumps(capture, indent=2), encoding="utf-8")
    result = rerank(
        capture, model_name=args.model,
        ollama_base_url=args.ollama_base_url,
        cache_dir=args.cache_dir,
        batch_size=args.batch_size,
    )
    result["capture"] = str(args.capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "complete": result["complete"],
        "candidate_count": result["candidate_count"],
        "document_cache_reused": result["document_cache_reused"],
        "elapsed_seconds": result["elapsed_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
