"""Evaluate local embedding candidates against retained CineGraph evidence.

This is deliberately an evaluation tool, not a retrieval service.  It writes
no vectors to the database and never turns a semantic match into a fact.  The
golden targets are the exact narrative passages already linked to curated
research answers.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CanonicalEntity, EvidenceChunk, EvidenceChunkRun, ResearchAnswer, ResearchAnswerEvidence
from app.services.lexical_retrieval import Bm25Index, reciprocal_rank_fusion
from app.services.embedding_artifacts import DOCUMENT_REPRESENTATION, document_cache_key
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.retrieval_routing import narrative_section_candidates


MODEL_CANDIDATES = (
    "BAAI/bge-small-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
)
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MODEL_INPUT_LIMITS = {
    "BAAI/bge-small-en-v1.5": 512,
    "sentence-transformers/all-MiniLM-L6-v2": 256,
}


def query_text(model_name: str, question: str) -> str:
    return f"{BGE_QUERY_PREFIX}{question}" if model_name == "BAAI/bge-small-en-v1.5" else question


def ranking_metrics(
    ranked_chunk_ids: Iterable[str],
    target_chunk_ids: set[str],
    *,
    cutoff: int = 10,
) -> dict[str, float | int | None]:
    """Score one result list against retained evidence; fully deterministic."""
    ranked = list(ranked_chunk_ids)[:cutoff]
    first_rank = next((index for index, chunk_id in enumerate(ranked, start=1) if chunk_id in target_chunk_ids), None)
    return {
        "recall": int(first_rank is not None),
        "reciprocal_rank": (1 / first_rank) if first_rank else 0.0,
        "first_relevant_rank": first_rank,
    }


def summary_metrics(per_query: list[dict[str, Any]], *, cutoff: int) -> dict[str, float | int]:
    if not per_query:
        return {"evaluated_queries": 0, f"recall_at_{cutoff}": 0.0, f"mrr_at_{cutoff}": 0.0}
    return {
        "evaluated_queries": len(per_query),
        f"recall_at_{cutoff}": round(sum(item["recall"] for item in per_query) / len(per_query), 4),
        f"mrr_at_{cutoff}": round(sum(item["reciprocal_rank"] for item in per_query) / len(per_query), 4),
    }


def _candidate_run(db: Session, collection_code: str, chunker_version: str | None) -> EvidenceChunkRun:
    query = select(EvidenceChunkRun).where(
        EvidenceChunkRun.collection_code == collection_code,
        EvidenceChunkRun.status == "complete",
    )
    if chunker_version:
        query = query.where(EvidenceChunkRun.chunker_version == chunker_version)
    run = db.scalar(query.order_by(EvidenceChunkRun.completed_at.desc()))
    if run is None:
        raise ValueError("No completed evidence-chunk run matches the requested collection/version.")
    return run


def _evaluation_rows(db: Session, run: EvidenceChunkRun) -> tuple[list[EvidenceChunk], list[dict[str, Any]]]:
    chunks = list(db.scalars(select(EvidenceChunk).where(
        EvidenceChunk.preprocessing_run_id == run.id,
        EvidenceChunk.quality_status == "eligible",
    ).order_by(EvidenceChunk.id)))
    chunk_ids_by_passage: dict[object, set[str]] = defaultdict(set)
    for chunk in chunks:
        chunk_ids_by_passage[chunk.narrative_passage_id].add(str(chunk.id))

    answers: dict[object, dict[str, Any]] = {}
    rows = db.execute(
        select(ResearchAnswer, ResearchAnswerEvidence.narrative_passage_id)
        .join(ResearchAnswerEvidence, ResearchAnswerEvidence.research_answer_id == ResearchAnswer.id)
        .where(ResearchAnswerEvidence.narrative_passage_id.is_not(None))
        .order_by(ResearchAnswer.id)
    ).all()
    for answer, passage_id in rows:
        target_chunk_ids = chunk_ids_by_passage.get(passage_id, set())
        if not target_chunk_ids:
            continue
        entry = answers.setdefault(str(answer.id), {
            "research_answer_id": str(answer.id),
            "subject_entity_id": str(answer.subject_entity_id),
            "question_id": answer.question_id,
            "question_text": answer.question_text,
            "evidence_class": answer.evidence_class,
            "target_chunk_ids": set(),
        })
        entry["target_chunk_ids"].update(target_chunk_ids)
    return chunks, list(answers.values())


def _model_metadata(model: Any, model_name: str) -> dict[str, Any]:
    supported = next((item for item in model.list_supported_models() if item["model"] == model_name), None)
    if supported is None:
        raise ValueError(f"FastEmbed does not expose the requested model {model_name!r}.")
    return {
        "name": model_name,
        "license": supported.get("license"),
        "dimension": supported.get("dim"),
        "size_in_gb": supported.get("size_in_GB"),
        "description": supported.get("description"),
        "source": supported.get("sources"),
    }


def _token_length_summary(model: Any, contents: list[str], *, max_input_tokens: int) -> dict[str, int]:
    tokenizer = model.model.tokenizer
    tokenizer.no_truncation()
    lengths = [len(tokenizer.encode(content).ids) for content in contents]
    # FastEmbed configures a truncating tokenizer for inference. Restore the
    # model-card limit after measuring the untruncated source input.  Keep the
    # limit explicit and versioned here instead of relying on a private runtime
    # attribute that FastEmbed does not expose consistently.
    tokenizer.enable_truncation(max_length=max_input_tokens)
    return {
        "max_input_tokens": max_input_tokens,
        "over_limit_chunks": sum(length > max_input_tokens for length in lengths),
        "maximum_untruncated_tokens": max(lengths, default=0),
    }


def _rank_evaluation(
    *,
    chunks: list[EvidenceChunk],
    queries: list[dict[str, Any]],
    matrix: np.ndarray,
    query_vectors: np.ndarray,
    cutoff: int,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    chunk_ids = np.asarray([str(chunk.id) for chunk in chunks])
    per_query: list[dict[str, Any]] = []
    for query, vector in zip(queries, query_vectors, strict=True):
        scores = matrix @ vector
        top_indexes = np.argpartition(scores, -cutoff)[-cutoff:]
        top_indexes = top_indexes[np.argsort(scores[top_indexes])[::-1]]
        metrics = ranking_metrics((chunk_ids[index] for index in top_indexes), query["target_chunk_ids"], cutoff=cutoff)
        per_query.append({
            "research_answer_id": query["research_answer_id"],
            "question_id": query["question_id"],
            "evidence_class": query["evidence_class"],
            "target_count": len(query["target_chunk_ids"]),
            **metrics,
        })
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in per_query:
        by_class[row["evidence_class"]].append(row)
    return per_query, by_class


def _metrics_for_rankings(
    queries: list[dict[str, Any]],
    rankings: list[list[str]],
    *,
    cutoff: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query, ranking in zip(queries, rankings, strict=True):
        metrics = ranking_metrics(ranking, query["target_chunk_ids"], cutoff=cutoff)
        row = {
            "research_answer_id": query["research_answer_id"],
            "question_id": query["question_id"],
            "evidence_class": query["evidence_class"],
            **metrics,
        }
        rows.append(row)
        groups[row["evidence_class"]].append(row)
    return {
        "overall": summary_metrics(rows, cutoff=cutoff),
        "by_evidence_class": {key: summary_metrics(items, cutoff=cutoff) for key, items in sorted(groups.items())},
        "per_query": rows,
    }


def _reranker_candidate_manifest(
    *,
    chunks: list[EvidenceChunk],
    contents: list[str],
    queries: list[dict[str, Any]],
    rankings_by_method: dict[str, list[list[str]]],
    candidate_limit: int = 20,
) -> dict[str, Any]:
    """Export bounded, source-linked candidates for an isolated reranker.

    Model weights live outside the application environment, so the cross
    encoder consumes this local manifest instead of importing the database or
    silently reaching an external source. Only narrative questions belong in
    this lane.
    """
    content_by_chunk_id = {
        str(chunk.id): {
            "chunk_id": str(chunk.id),
            "subject_entity_id": str(chunk.subject_entity_id),
            "section_locator": chunk.section_locator,
            "document": content,
        }
        for chunk, content in zip(chunks, contents, strict=True)
    }
    narrative_indexes = [
        index for index, query in enumerate(queries)
        if query["evidence_class"] == "narrative_extraction"
    ]
    return {
        "manifest_version": "cinegraph-reranker-candidates-v1",
        "instruction": (
            "Given a film research question, rank passages that directly answer the question. "
            "Prefer explicit source evidence over broad thematic similarity."
        ),
        "candidate_limit": candidate_limit,
        "queries": [
            {
                "research_answer_id": queries[index]["research_answer_id"],
                "question_id": queries[index]["question_id"],
                "question_text": queries[index]["question_text"],
                "evidence_class": queries[index]["evidence_class"],
                "target_chunk_ids": sorted(queries[index]["target_chunk_ids"]),
                "methods": {
                    method: [
                        content_by_chunk_id[chunk_id]
                        for chunk_id in rankings[index][:candidate_limit]
                    ]
                    for method, rankings in rankings_by_method.items()
                },
            }
            for index in narrative_indexes
        ],
    }


def _contextual_evidence_texts(db: Session, chunks: list[EvidenceChunk]) -> list[str]:
    labels = _canonical_labels(db, chunks)
    return [
        f"Film: {labels[chunk.subject_entity_id]}\nSection: {chunk.section_title}\nEvidence: {chunk.content}"
        for chunk in chunks
    ]


def _canonical_labels(db: Session, chunks: list[EvidenceChunk]) -> dict[object, str]:
    return dict(db.execute(select(CanonicalEntity.id, CanonicalEntity.canonical_label).where(
        CanonicalEntity.id.in_({chunk.subject_entity_id for chunk in chunks})
    )).all())


def _rank_indexes(scores: np.ndarray, candidate_indexes: np.ndarray, *, cutoff: int) -> np.ndarray:
    """Rank a bounded candidate set without assuming it contains ``cutoff`` rows."""
    if not len(candidate_indexes):
        return candidate_indexes
    selected_count = min(cutoff, len(candidate_indexes))
    candidate_scores = scores[candidate_indexes]
    if selected_count == len(candidate_indexes):
        selected = np.arange(len(candidate_indexes))
    else:
        selected = np.argpartition(candidate_scores, -selected_count)[-selected_count:]
    return candidate_indexes[selected[np.argsort(candidate_scores[selected])[::-1]]]


def _section_matches_question_route(*, section_locator: str, question_id: str, evidence_class: str) -> bool:
    """Apply a declared question-catalog route before semantic ranking.

    This is intentionally narrow. It improves evidence precision for story and
    structure questions without learning section names from benchmark scores.
    Other evidence classes retain their dedicated structured/critical routes.
    """
    candidates = narrative_section_candidates(question_id=question_id, evidence_class=evidence_class)
    if not candidates:
        return True
    locator_parts = {part.casefold() for part in section_locator.split("/")}
    return bool(locator_parts & set(candidates))


def _batch_ollama_embeddings(
    client: OllamaEmbeddingClient,
    values: list[str],
    *,
    profile: OllamaEmbeddingProfile,
    batch_size: int,
    label: str,
) -> np.ndarray:
    batches: list[list[float]] = []
    for offset in range(0, len(values), batch_size):
        batch = values[offset: offset + batch_size]
        batches.extend(client.embed(batch, profile=profile))
        print(f"[{profile.model}] {label}: {min(offset + len(batch), len(values)):,}/{len(values):,}", flush=True)
    return np.asarray(batches, dtype=np.float32)


def _document_cache_key(*, profile: OllamaEmbeddingProfile, run: EvidenceChunkRun, contents: list[str]) -> str:
    return document_cache_key(
        provider="ollama",
        model_name=profile.model,
        dimensions=profile.dimensions,
        chunk_run_id=str(run.id),
        chunker_version=run.chunker_version,
        contents=contents,
    )


def _cached_ollama_document_embeddings(
    client: OllamaEmbeddingClient,
    contents: list[str],
    *,
    profile: OllamaEmbeddingProfile,
    run: EvidenceChunkRun,
    batch_size: int,
    cache_dir: Path | None,
) -> tuple[np.ndarray, bool]:
    if cache_dir is None:
        return _batch_ollama_embeddings(client, contents, profile=profile, batch_size=batch_size, label="evidence chunks"), False
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _document_cache_key(profile=profile, run=run, contents=contents)
    vector_path = cache_dir / f"{profile.model.replace('/', '--').replace(':', '--')}-{key}.npy"
    partial_path = vector_path.with_suffix(".partial.npy")
    progress_path = vector_path.with_suffix(".progress.json")
    if vector_path.exists():
        matrix = np.load(vector_path, allow_pickle=False)
        if matrix.shape == (len(contents), profile.dimensions):
            print(f"[{profile.model}] reusing local document-vector cache {vector_path.name}", flush=True)
            return matrix.astype(np.float32, copy=False), True
        vector_path.unlink()

    next_offset = 0
    expected_shape = (len(contents), profile.dimensions)
    if partial_path.exists() and progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            candidate = np.lib.format.open_memmap(partial_path, mode="r+")
            if progress.get("cache_key") == key and candidate.shape == expected_shape:
                next_offset = int(progress["next_offset"])
                if not 0 <= next_offset <= len(contents):
                    raise ValueError("checkpoint offset is outside the corpus")
                matrix = candidate
                print(f"[{profile.model}] resuming local document-vector cache at {next_offset:,}/{len(contents):,}", flush=True)
            else:
                raise ValueError("checkpoint identity or shape does not match")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            partial_path.unlink(missing_ok=True)
            progress_path.unlink(missing_ok=True)
            next_offset = 0

    if next_offset == 0:
        matrix = np.lib.format.open_memmap(partial_path, mode="w+", dtype=np.float32, shape=expected_shape)

    for offset in range(next_offset, len(contents), batch_size):
        batch = contents[offset: offset + batch_size]
        vectors = np.asarray(client.embed(batch, profile=profile), dtype=np.float32)
        expected_batch_shape = (len(batch), profile.dimensions)
        if vectors.shape != expected_batch_shape:
            raise RuntimeError(f"Ollama returned matrix shape {vectors.shape}, expected {expected_batch_shape}.")
        end = offset + len(batch)
        matrix[offset:end] = vectors
        matrix.flush()
        temporary_progress_path = progress_path.with_suffix(".json.tmp")
        temporary_progress_path.write_text(
            json.dumps({"cache_key": key, "next_offset": end}, sort_keys=True),
            encoding="utf-8",
        )
        temporary_progress_path.replace(progress_path)
        print(f"[{profile.model}] evidence chunks: {end:,}/{len(contents):,}", flush=True)

    matrix.flush()
    del matrix
    partial_path.replace(vector_path)
    progress_path.unlink(missing_ok=True)
    return np.load(vector_path, allow_pickle=False).astype(np.float32, copy=False), False


def evaluate_model(
    db: Session,
    *,
    model_name: str,
    collection_code: str,
    chunker_version: str | None = None,
    cutoff: int = 10,
    batch_size: int = 128,
) -> dict[str, Any]:
    """Benchmark a local model without persisting vectors or changing facts."""
    try:
        from fastembed import TextEmbedding
        import fastembed
    except ImportError as exc:  # pragma: no cover - environment instruction
        raise RuntimeError("Install the optional local evaluator dependency: python -m pip install fastembed") from exc

    run = _candidate_run(db, collection_code, chunker_version)
    chunks, queries = _evaluation_rows(db, run)
    if not chunks or not queries:
        raise ValueError("Evaluation requires eligible chunks and research answers with linked narrative evidence.")
    model = TextEmbedding(model_name=model_name)
    metadata = _model_metadata(TextEmbedding, model_name)
    contents = _contextual_evidence_texts(db, chunks)
    print(f"[{model_name}] embedding {len(contents):,} evidence chunks", flush=True)
    document_started = time.perf_counter()
    matrix = np.asarray(list(model.embed(contents, batch_size=batch_size)), dtype=np.float32)
    document_seconds = time.perf_counter() - document_started
    query_inputs = [query_text(model_name, item["question_text"]) for item in queries]
    print(f"[{model_name}] embedding {len(query_inputs):,} evidence-linked questions", flush=True)
    query_started = time.perf_counter()
    query_vectors = np.asarray(list(model.embed(query_inputs, batch_size=batch_size)), dtype=np.float32)
    query_seconds = time.perf_counter() - query_started

    print(f"[{model_name}] scoring {len(query_inputs):,} questions against {len(contents):,} chunks", flush=True)

    per_query, by_class = _rank_evaluation(
        chunks=chunks, queries=queries, matrix=matrix, query_vectors=query_vectors, cutoff=cutoff,
    )
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "collection_code": collection_code,
        "chunk_run": {"id": str(run.id), "chunker_version": run.chunker_version, "configuration_hash": run.configuration_hash},
        "model": {**metadata, "fastembed_version": fastembed.__version__},
        "corpus": {
            "eligible_chunk_count": len(chunks),
            "embedding_matrix_bytes": int(matrix.nbytes),
            **_token_length_summary(model, contents, max_input_tokens=MODEL_INPUT_LIMITS[model_name]),
        },
        "timing": {
            "document_embedding_seconds": round(document_seconds, 4),
            "documents_per_second": round(len(chunks) / document_seconds, 2),
            "query_embedding_seconds": round(query_seconds, 4),
            "query_embedding_milliseconds_each": round(query_seconds * 1000 / len(queries), 3),
        },
        "metrics": {
            "overall": summary_metrics(per_query, cutoff=cutoff),
            "by_evidence_class": {key: summary_metrics(rows, cutoff=cutoff) for key, rows in sorted(by_class.items())},
        },
        "per_query": per_query,
    }


def evaluate_ollama_model(
    db: Session,
    *,
    collection_code: str,
    chunker_version: str | None = None,
    profile: OllamaEmbeddingProfile | None = None,
    cutoff: int = 10,
    batch_size: int = 24,
    cache_dir: Path | None = None,
    evaluation_scope: str = "full",
    export_reranker_candidates: bool = False,
) -> dict[str, Any]:
    """Evaluate local Ollama vectors without writing vectors or facts."""
    profile = profile or OllamaEmbeddingProfile()
    run = _candidate_run(db, collection_code, chunker_version)
    chunks, queries = _evaluation_rows(db, run)
    if not chunks or not queries:
        raise ValueError("Evaluation requires eligible chunks and research answers with linked narrative evidence.")
    if evaluation_scope not in {"full", "benchmark_subjects"}:
        raise ValueError("evaluation_scope must be 'full' or 'benchmark_subjects'.")
    if evaluation_scope == "benchmark_subjects":
        benchmark_subject_ids = {query["subject_entity_id"] for query in queries}
        chunks = [chunk for chunk in chunks if str(chunk.subject_entity_id) in benchmark_subject_ids]
    client = OllamaEmbeddingClient()
    contents = _contextual_evidence_texts(db, chunks)
    labels = _canonical_labels(db, chunks)
    labels_by_string_id = {str(identifier): label for identifier, label in labels.items()}
    document_started = time.perf_counter()
    matrix, document_cache_reused = _cached_ollama_document_embeddings(
        client, contents, profile=profile, run=run, batch_size=batch_size, cache_dir=cache_dir,
    )
    document_seconds = time.perf_counter() - document_started
    query_inputs = [profile.query_input(item["question_text"]) for item in queries]
    query_started = time.perf_counter()
    query_vectors = _batch_ollama_embeddings(
        client, query_inputs, profile=profile, batch_size=batch_size, label="evidence-linked questions",
    )
    title_aware_inputs = [
        profile.query_input(
            f"Film: {labels_by_string_id[item['subject_entity_id']]}"
            f"\nQuestion: {item['question_text']}"
        )
        for item in queries
    ]
    title_aware_query_vectors = _batch_ollama_embeddings(
        client, title_aware_inputs, profile=profile, batch_size=batch_size, label="title-aware questions",
    )
    query_seconds = time.perf_counter() - query_started
    candidate_cutoff = max(100, cutoff)
    chunk_ids = np.asarray([str(chunk.id) for chunk in chunks])
    lexical = Bm25Index.build(contents)
    dense_rankings: list[list[str]] = []
    title_aware_dense_rankings: list[list[str]] = []
    film_scoped_rankings: list[list[str]] = []
    title_aware_film_scoped_rankings: list[list[str]] = []
    section_routed_film_scoped_rankings: list[list[str]] = []
    lexical_rankings: list[list[str]] = []
    fused_rankings: list[list[str]] = []
    subject_ids = np.asarray([str(chunk.subject_entity_id) for chunk in chunks])
    all_indexes = np.arange(len(chunks))
    for query, vector, title_aware_vector in zip(queries, query_vectors, title_aware_query_vectors, strict=True):
        scores = matrix @ vector
        title_aware_scores = matrix @ title_aware_vector
        indexes = _rank_indexes(scores, all_indexes, cutoff=candidate_cutoff)
        title_aware_indexes = _rank_indexes(title_aware_scores, all_indexes, cutoff=candidate_cutoff)
        film_indexes = np.flatnonzero(subject_ids == query["subject_entity_id"])
        scoped_indexes = _rank_indexes(scores, film_indexes, cutoff=candidate_cutoff)
        title_aware_scoped_indexes = _rank_indexes(title_aware_scores, film_indexes, cutoff=candidate_cutoff)
        section_indexes = np.asarray([
            index for index in film_indexes
            if _section_matches_question_route(
                section_locator=chunks[index].section_locator,
                question_id=query["question_id"],
                evidence_class=query["evidence_class"],
            )
        ], dtype=int)
        if not len(section_indexes):
            section_indexes = film_indexes
        section_routed_indexes = _rank_indexes(scores, section_indexes, cutoff=candidate_cutoff)
        dense = [str(chunk_ids[index]) for index in indexes]
        title_aware_dense = [str(chunk_ids[index]) for index in title_aware_indexes]
        film_scoped = [str(chunk_ids[index]) for index in scoped_indexes]
        title_aware_film_scoped = [str(chunk_ids[index]) for index in title_aware_scoped_indexes]
        section_routed_film_scoped = [str(chunk_ids[index]) for index in section_routed_indexes]
        sparse = [str(chunk_ids[index]) for index in lexical.rank(query["question_text"], cutoff=candidate_cutoff)]
        dense_rankings.append(dense)
        title_aware_dense_rankings.append(title_aware_dense)
        film_scoped_rankings.append(film_scoped)
        title_aware_film_scoped_rankings.append(title_aware_film_scoped)
        section_routed_film_scoped_rankings.append(section_routed_film_scoped)
        lexical_rankings.append(sparse)
        fused_rankings.append(reciprocal_rank_fusion([dense, sparse], cutoff=candidate_cutoff))
    dense_metrics = _metrics_for_rankings(queries, dense_rankings, cutoff=cutoff)
    title_aware_dense_metrics = _metrics_for_rankings(queries, title_aware_dense_rankings, cutoff=cutoff)
    film_scoped_metrics = _metrics_for_rankings(queries, film_scoped_rankings, cutoff=cutoff)
    title_aware_film_scoped_metrics = _metrics_for_rankings(queries, title_aware_film_scoped_rankings, cutoff=cutoff)
    section_routed_film_scoped_metrics = _metrics_for_rankings(queries, section_routed_film_scoped_rankings, cutoff=cutoff)
    lexical_metrics = _metrics_for_rankings(queries, lexical_rankings, cutoff=cutoff)
    fusion_metrics = _metrics_for_rankings(queries, fused_rankings, cutoff=cutoff)
    per_query, by_class = _rank_evaluation(
        chunks=chunks, queries=queries, matrix=matrix, query_vectors=query_vectors, cutoff=cutoff,
    )
    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "collection_code": collection_code,
        "chunk_run": {"id": str(run.id), "chunker_version": run.chunker_version, "configuration_hash": run.configuration_hash},
        "model": {
            "provider": "ollama", "name": profile.model, "dimension": profile.dimensions,
            "context_window": profile.context_window, "query_instruction": profile.query_instruction,
        },
        "corpus": {
            "eligible_chunk_count": len(chunks), "embedding_matrix_bytes": int(matrix.nbytes),
            "evaluation_scope": evaluation_scope,
            "max_input_tokens": profile.context_window, "over_limit_chunks": 0,
            "overflow_policy": "ollama_truncate_false",
            "document_representation": DOCUMENT_REPRESENTATION,
            "document_vector_cache_reused": document_cache_reused,
        },
        "timing": {
            "document_embedding_seconds": round(document_seconds, 4),
            "documents_per_second": round(len(chunks) / document_seconds, 2),
            "query_embedding_seconds": round(query_seconds, 4),
            "query_embedding_milliseconds_each": round(query_seconds * 1000 / len(queries), 3),
        },
        "metrics": {
            "overall": summary_metrics(per_query, cutoff=cutoff),
            "by_evidence_class": {key: summary_metrics(rows, cutoff=cutoff) for key, rows in sorted(by_class.items())},
        },
        "retrieval_methods": {
            "dense_global_question_only": dense_metrics,
            "dense_global_title_aware": title_aware_dense_metrics,
            "dense_film_scoped_question_only": film_scoped_metrics,
            "dense_film_scoped_title_aware": title_aware_film_scoped_metrics,
            "dense_film_scoped_section_routed": section_routed_film_scoped_metrics,
            "bm25": lexical_metrics,
            "reciprocal_rank_fusion": fusion_metrics,
        },
        "per_query": per_query,
    }
    if export_reranker_candidates:
        report["reranker_candidate_manifest"] = _reranker_candidate_manifest(
            chunks=chunks,
            contents=contents,
            queries=queries,
            rankings_by_method={
                "dense_film_scoped_question_only": film_scoped_rankings,
                "dense_film_scoped_section_routed": section_routed_film_scoped_rankings,
            },
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate local embedding candidates against source-linked CineGraph narrative evidence.")
    parser.add_argument("--collection", default="english-1000-retained-narrative-v1")
    parser.add_argument("--chunker-version", default="spacy-sentencizer-evidence-v3")
    parser.add_argument("--model", action="append", choices=MODEL_CANDIDATES, help="Repeat to select candidates; default evaluates both.")
    parser.add_argument("--cutoff", type=int, default=10)
    parser.add_argument("--output-dir", default="data/evaluation")
    parser.add_argument("--provider", choices=("fastembed", "ollama"), default="fastembed")
    parser.add_argument("--ollama-model", default="qwen3-embedding:0.6b")
    parser.add_argument("--ollama-dimensions", type=int, default=1024)
    parser.add_argument("--ollama-context-window", type=int, default=32_000)
    parser.add_argument("--evaluation-scope", choices=("full", "benchmark_subjects"), default="full")
    parser.add_argument("--export-reranker-candidates", action="store_true")
    parser.add_argument("--batch-size", type=int, default=24)
    arguments = parser.parse_args()
    models = arguments.model or list(MODEL_CANDIDATES)
    output_dir = Path(arguments.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        if arguments.provider == "ollama":
            profile = OllamaEmbeddingProfile(
                model=arguments.ollama_model,
                dimensions=arguments.ollama_dimensions,
                context_window=arguments.ollama_context_window,
            )
            report = evaluate_ollama_model(
                db,
                collection_code=arguments.collection,
                chunker_version=arguments.chunker_version,
                cutoff=arguments.cutoff,
                cache_dir=output_dir / "cache",
                profile=profile,
                evaluation_scope=arguments.evaluation_scope,
                batch_size=arguments.batch_size,
                export_reranker_candidates=arguments.export_reranker_candidates,
            )
            output = output_dir / (
                f"ollama--{report['model']['name'].replace('/', '--').replace(':', '--')}-"
                f"{report['corpus']['evaluation_scope']}-{report['chunk_run']['chunker_version']}.json"
            )
            candidate_manifest = report.pop("reranker_candidate_manifest", None)
            output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            if candidate_manifest is not None:
                candidate_output = output.with_name(f"{output.stem}--reranker-candidates.json")
                candidate_output.write_text(json.dumps(candidate_manifest, indent=2, sort_keys=True), encoding="utf-8")
                print(f"Reranker candidate manifest: {candidate_output}", flush=True)
            print(json.dumps({"model": report["model"], "output": str(output), "metrics": report["metrics"], "corpus": report["corpus"], "timing": report["timing"]}, indent=2))
            return
        for model_name in models:
            report = evaluate_model(
                db,
                model_name=model_name,
                collection_code=arguments.collection,
                chunker_version=arguments.chunker_version,
                cutoff=arguments.cutoff,
            )
            output = output_dir / f"{model_name.replace('/', '--')}-{report['chunk_run']['chunker_version']}.json"
            output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            print(json.dumps({"model": model_name, "output": str(output), "metrics": report["metrics"], "corpus": report["corpus"], "timing": report["timing"]}, indent=2))


if __name__ == "__main__":
    main()
