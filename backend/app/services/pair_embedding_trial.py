"""Offline Qwen embedding candidate capture for the frozen pair-relevance study.

Embeddings and captured passages are local evaluation artifacts. This module is
read-only with respect to PostgreSQL and never writes facts or vectors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from sqlalchemy import select, text

from app.db import SessionLocal, settings
from app.models import CanonicalEntity, EvidenceChunk, EvidenceChunkRun
from app.services.embedding_evaluation import _cached_ollama_document_embeddings
from app.services.ollama_embeddings import (
    QWEN_FILM_RETRIEVAL_INSTRUCTION,
    OllamaEmbeddingClient,
    OllamaEmbeddingProfile,
)
from app.services.pair_relevance_eval import validate_manifest


def trial_question_texts(query_rows: list[tuple], *, film_context: bool) -> list[str]:
    if not film_context:
        return [question for _pair, _ordinal, question in query_rows]
    return [f"Film: {title}\nResearch question: {question}"
            for pair, _ordinal, question in query_rows for title in pair["titles"]]


def rank_film_candidates(
    *,
    film_entity_id: str,
    chunks: list[EvidenceChunk],
    matrix: np.ndarray,
    query_vector: np.ndarray,
    limit: int,
) -> list[dict]:
    """Rank only one film's passages by normalized cosine similarity."""
    if matrix.ndim != 2 or query_vector.ndim != 1 or matrix.shape[1] != query_vector.shape[0]:
        raise ValueError("Embedding matrix and query vector dimensions must match.")
    if matrix.shape[0] != len(chunks):
        raise ValueError("One document vector is required per evidence chunk.")
    if limit < 1:
        raise ValueError("Candidate limit must be positive.")
    indexes = [index for index, chunk in enumerate(chunks)
               if str(chunk.subject_entity_id) == film_entity_id]
    if not indexes:
        return []
    film_vectors = matrix[indexes]
    film_norms = np.linalg.norm(film_vectors, axis=1)
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0 or np.any(film_norms == 0):
        raise ValueError("Zero-length embeddings cannot be ranked.")
    scores = (film_vectors @ query_vector) / (film_norms * query_norm)
    ranked_local = np.argsort(-scores, kind="stable")[:limit]
    result = []
    for rank, local_index in enumerate(ranked_local, start=1):
        chunk = chunks[indexes[int(local_index)]]
        result.append({
            "chunk_id": str(chunk.id),
            "subject_entity_id": str(chunk.subject_entity_id),
            "source_snapshot_id": str(chunk.source_snapshot_id),
            "section_locator": chunk.section_locator,
            "section_title": chunk.section_title,
            "content": chunk.content,
            "rank": rank,
            "fused_score": None,
            "semantic_similarity": round(float(scores[int(local_index)]), 6),
            "lexical_score": None,
            "matched_by": ["semantic"],
        })
    return result


def capture(
    manifest: dict,
    *,
    model_name: str,
    ollama_base_url: str,
    cache_dir: Path,
    candidate_limit: int = 10,
    batch_size: int = 16,
    pair_count: int = 10,
    collection_code: str | None = None,
    dimensions: int = 1024,
    film_context: bool = False,
) -> dict:
    validate_manifest(manifest)
    if not 1 <= pair_count <= len(manifest["pairs"]):
        raise ValueError("Select a non-empty frozen prefix of film pairs.")
    manifest = {**manifest, "pairs": manifest["pairs"][:pair_count],
                "collection": collection_code or manifest["collection"]}
    from sqlalchemy.engine.url import make_url

    if make_url(settings.database_url).database != "cinegraph_eval":
        raise RuntimeError("Pair embedding evaluation may run only against cinegraph_eval.")
    if candidate_limit < 1 or batch_size < 1:
        raise ValueError("Candidate and batch sizes must be positive.")

    qids = {qid for pair in manifest["pairs"] for qid in pair["films"]}
    profile = OllamaEmbeddingProfile(
        model=model_name,
        dimensions=dimensions,
        query_instruction=QWEN_FILM_RETRIEVAL_INSTRUCTION,
    )
    client = OllamaEmbeddingClient(base_url=ollama_base_url, timeout_seconds=300)
    started = perf_counter()
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        entity_rows = db.execute(select(
            CanonicalEntity.wikidata_id, CanonicalEntity.id, CanonicalEntity.canonical_label,
        ).where(CanonicalEntity.wikidata_id.in_(qids))).all()
        entities = {qid: (str(entity_id), label) for qid, entity_id, label in entity_rows}
        if qids - entities.keys():
            raise ValueError(f"Films missing from evaluation DB: {sorted(qids - entities.keys())}")
        run = db.scalar(select(EvidenceChunkRun).where(
            EvidenceChunkRun.collection_code == manifest["collection"],
            EvidenceChunkRun.status == "complete",
        ).order_by(EvidenceChunkRun.completed_at.desc().nulls_last(), EvidenceChunkRun.id).limit(1))
        if run is None:
            raise ValueError("No completed evidence chunk run matches the frozen collection.")
        entity_ids = {entity_id for entity_id, _label in entities.values()}
        chunks = list(db.scalars(select(EvidenceChunk).where(
            EvidenceChunk.preprocessing_run_id == run.id,
            EvidenceChunk.quality_status == "eligible",
            EvidenceChunk.subject_entity_id.in_(entity_ids),
        ).order_by(EvidenceChunk.id)))
        labels = {entity_id: label for entity_id, label in entities.values()}
        contents = [
            f"Film: {labels[str(chunk.subject_entity_id)]}\nSection: {chunk.section_title}\nEvidence: {chunk.content}"
            for chunk in chunks
        ]
        document_matrix, cache_reused = _cached_ollama_document_embeddings(
            client, contents, profile=profile, run=run,
            batch_size=batch_size, cache_dir=cache_dir,
        )
        query_rows = [
            (pair, ordinal, question)
            for pair in manifest["pairs"]
            for ordinal, question in enumerate(pair["questions"], start=1)
        ]
        question_texts = trial_question_texts(query_rows, film_context=film_context)
        query_vectors: list[list[float]] = []
        for offset in range(0, len(question_texts), batch_size):
            batch = question_texts[offset: offset + batch_size]
            query_vectors.extend(client.embed(
                [profile.query_input(question) for question in batch],
                profile=profile,
            ))
            print(f"[{model_name}] pair questions: {min(offset + len(batch), len(question_texts))}/{len(question_texts)}", flush=True)

        cases = []
        for query_index, (pair, ordinal, question) in enumerate(query_rows):
            side_pools = []
            for side_index, qid in enumerate(pair["films"]):
                entity_id, _title = entities[qid]
                side_pools.append(rank_film_candidates(
                    film_entity_id=entity_id,
                    chunks=chunks,
                    matrix=document_matrix,
                    query_vector=np.asarray(query_vectors[query_index * 2 + side_index if film_context else query_index], dtype=np.float32),
                    limit=candidate_limit,
                ))
            case = {
                "case_id": f"{pair['id']}-Q{ordinal}",
                "pair_id": pair["id"],
                "film_qids": pair["films"],
                "titles": pair["titles"],
                "question": question,
                "answerability_status": "not_assessed",
                "answerability_reason": "Offline embedding candidate ranking; answerability is not inferred.",
                "retrieval_method": f"{model_name}-film-scoped",
                "degraded": False,
                "fallback_reason": None,
                "preprocessing_run_id": str(run.id),
                "index_run_id": None,
                "elapsed_ms": None,
                "first_options": side_pools[0][:3],
                "second_options": side_pools[1][:3],
                "first_pool": side_pools[0],
                "second_pool": side_pools[1],
                "other_lenses": [],
            }
            cases.append(case)
            print(f"{len(cases):02d}/{len(query_rows)} {case['case_id']}", flush=True)

    elapsed = round((perf_counter() - started) * 1000, 1)
    return {
        "manifest_version": manifest["version"],
        "method": f"{model_name}-film-scoped",
        "model": model_name,
        "dimension": profile.dimensions,
        "query_instruction": profile.query_instruction,
        "query_context": "target-film-title" if film_context else "shared-question",
        "document_representation": "film-section-evidence-v1",
        "preprocessing_run_id": str(run.id),
        "eligible_chunk_count": len(chunks),
        "document_cache_reused": cache_reused,
        "candidate_limit": candidate_limit,
        "elapsed_ms": elapsed,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--model", default="qwen3-embedding:4b")
    parser.add_argument("--ollama-base-url", default=settings.ollama_base_url)
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--pairs", type=int, default=10)
    parser.add_argument("--collection")
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--film-context", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = capture(
        manifest,
        model_name=args.model,
        ollama_base_url=args.ollama_base_url,
        cache_dir=args.cache_dir,
        candidate_limit=args.candidate_limit,
        batch_size=args.batch_size,
        pair_count=args.pairs, collection_code=args.collection, dimensions=args.dimensions,
        film_context=args.film_context,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "cases": len(result["cases"]),
        "eligible_chunk_count": result["eligible_chunk_count"],
        "document_cache_reused": result["document_cache_reused"],
        "elapsed_ms": result["elapsed_ms"],
    }, indent=2))


if __name__ == "__main__":
    main()
