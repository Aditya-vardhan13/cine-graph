"""Validate the persisted narrative retrieval path end to end."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.embedding_evaluation import _candidate_run, _evaluation_rows, ranking_metrics, summary_metrics
from app.services.evidence_retrieval import retrieve_narrative_evidence


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def validate_persisted_retrieval(
    db: Session,
    *,
    collection_code: str,
    chunker_version: str,
    model_name: str,
    cutoff: int = 10,
) -> dict:
    chunk_run = _candidate_run(db, collection_code, chunker_version)
    _, all_queries = _evaluation_rows(db, chunk_run)
    queries = [query for query in all_queries if query["evidence_class"] == "narrative_extraction"]
    rows = []
    embedding_latencies = []
    database_latencies = []
    for index, query in enumerate(queries, start=1):
        result = retrieve_narrative_evidence(
            db,
            subject_entity_id=UUID(query["subject_entity_id"]),
            question_id=query["question_id"],
            question_text=query["question_text"],
            evidence_class=query["evidence_class"],
            limit=cutoff,
            model_name=model_name,
        )
        metrics = ranking_metrics(
            [item.chunk_id for item in result.evidence],
            query["target_chunk_ids"],
            cutoff=cutoff,
        )
        rows.append({
            "research_answer_id": query["research_answer_id"],
            "question_id": query["question_id"],
            **metrics,
        })
        embedding_latencies.append(result.query_embedding_milliseconds)
        database_latencies.append(result.database_ranking_milliseconds)
        print(f"persisted retrieval: {index}/{len(queries)}", flush=True)
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "collection_code": collection_code,
        "chunker_version": chunker_version,
        "metrics": summary_metrics(rows, cutoff=cutoff),
        "latency_milliseconds": {
            "query_embedding_p50": round(median(embedding_latencies), 3) if embedding_latencies else 0.0,
            "query_embedding_p95": round(percentile(embedding_latencies, 0.95), 3),
            "database_ranking_p50": round(median(database_latencies), 3) if database_latencies else 0.0,
            "database_ranking_p95": round(percentile(database_latencies, 0.95), 3),
        },
        "per_query": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CineGraph's persisted local narrative retrieval path.")
    parser.add_argument("--collection", default="english-1000-retained-narrative-v1")
    parser.add_argument("--chunker-version", default="spacy-sentencizer-evidence-v3")
    parser.add_argument("--model", default="qwen3-embedding:0.6b")
    parser.add_argument("--cutoff", type=int, default=10)
    parser.add_argument("--output", default="data/evaluation/persisted-narrative-retrieval.json")
    arguments = parser.parse_args()
    with SessionLocal() as db:
        report = validate_persisted_retrieval(
            db,
            collection_code=arguments.collection,
            chunker_version=arguments.chunker_version,
            model_name=arguments.model,
            cutoff=arguments.cutoff,
        )
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "metrics": report["metrics"], "latency_milliseconds": report["latency_milliseconds"]}, indent=2))


if __name__ == "__main__":
    main()
