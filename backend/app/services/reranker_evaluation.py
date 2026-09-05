"""Evaluate an isolated local cross-encoder over exported dense candidates.

The input is a retained, local candidate manifest produced by
``embedding_evaluation``. This process has no database or network-source write
path. Model downloads and weights remain in the user's Hugging Face cache.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODEL = "Qwen/Qwen3-Reranker-0.6B"


def rank_candidate_ids(candidates: list[dict[str, Any]], scores: list[float]) -> list[str]:
    if len(candidates) != len(scores):
        raise ValueError("candidate and score counts differ")
    ranked_indexes = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    return [candidates[index]["chunk_id"] for index in ranked_indexes]


def ranking_result(ranked_ids: list[str], target_ids: set[str], *, cutoff: int = 10) -> dict[str, Any]:
    first_rank = next(
        (rank for rank, chunk_id in enumerate(ranked_ids[:cutoff], start=1) if chunk_id in target_ids),
        None,
    )
    return {
        "recall": int(first_rank is not None),
        "reciprocal_rank": (1 / first_rank) if first_rank else 0.0,
        "first_relevant_rank": first_rank,
    }


def aggregate_results(rows: list[dict[str, Any]], *, cutoff: int = 10) -> dict[str, Any]:
    if not rows:
        return {"evaluated_queries": 0, f"recall_at_{cutoff}": 0.0, f"mrr_at_{cutoff}": 0.0}
    return {
        "evaluated_queries": len(rows),
        f"recall_at_{cutoff}": round(sum(row["recall"] for row in rows) / len(rows), 4),
        f"mrr_at_{cutoff}": round(sum(row["reciprocal_rank"] for row in rows) / len(rows), 4),
    }


def evaluate_manifest(
    manifest: dict[str, Any],
    *,
    score_pairs: Callable[[list[tuple[str, str]]], list[float]],
    cutoff: int = 10,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Rerank every declared candidate method and checkpoint per query."""
    method_rows: dict[str, list[dict[str, Any]]] = {}
    per_query: list[dict[str, Any]] = []
    started = time.perf_counter()
    for query_index, query in enumerate(manifest["queries"], start=1):
        for method, candidates in query["methods"].items():
            pairs = [(query["question_text"], candidate["document"]) for candidate in candidates]
            pair_started = time.perf_counter()
            scores = [float(score) for score in score_pairs(pairs)]
            elapsed = time.perf_counter() - pair_started
            ranked_ids = rank_candidate_ids(candidates, scores)
            result = {
                "research_answer_id": query["research_answer_id"],
                "question_id": query["question_id"],
                "candidate_method": method,
                "candidate_count": len(candidates),
                "rerank_seconds": round(elapsed, 4),
                **ranking_result(ranked_ids, set(query["target_chunk_ids"]), cutoff=cutoff),
            }
            method_rows.setdefault(method, []).append(result)
            per_query.append(result)
        if checkpoint is not None:
            checkpoint({
                "completed_queries": query_index,
                "total_queries": len(manifest["queries"]),
                "per_query": per_query,
            })
    return {
        "manifest_version": manifest["manifest_version"],
        "evaluated_queries": len(manifest["queries"]),
        "cutoff": cutoff,
        "timing": {
            "total_seconds": round(time.perf_counter() - started, 4),
            "seconds_per_query_method": round(
                sum(row["rerank_seconds"] for row in per_query) / len(per_query), 4,
            ) if per_query else 0.0,
        },
        "metrics_by_candidate_method": {
            method: aggregate_results(rows, cutoff=cutoff)
            for method, rows in sorted(method_rows.items())
        },
        "per_query": per_query,
    }


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a local cross-encoder over CineGraph candidates.")
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--cutoff", type=int, default=10)
    arguments = parser.parse_args()

    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:  # pragma: no cover - environment instruction
        raise RuntimeError("Install sentence-transformers in the isolated reranker environment.") from exc

    manifest_path = Path(arguments.manifest)
    output_path = Path(arguments.output)
    progress_path = output_path.with_suffix(f"{output_path.suffix}.progress")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = CrossEncoder(
        arguments.model,
        prompts={"cinegraph": manifest["instruction"]},
        default_prompt_name="cinegraph",
    )

    def score_pairs(pairs: list[tuple[str, str]]) -> list[float]:
        return model.predict(pairs, batch_size=arguments.batch_size, show_progress_bar=False).tolist()

    report = evaluate_manifest(
        manifest,
        score_pairs=score_pairs,
        cutoff=arguments.cutoff,
        checkpoint=lambda payload: _atomic_json_write(progress_path, payload),
    )
    report["model"] = {
        "name": arguments.model,
        "instruction": manifest["instruction"],
        "runtime": "sentence-transformers-cross-encoder",
    }
    report["input_manifest"] = str(manifest_path)
    _atomic_json_write(output_path, report)
    progress_path.unlink(missing_ok=True)
    print(json.dumps({"output": str(output_path), "metrics": report["metrics_by_candidate_method"], "timing": report["timing"]}, indent=2))


if __name__ == "__main__":
    main()
