"""Offline Apple-Silicon MLX trial for a quantized Qwen3 reranker.

Uses Qwen's yes/no logit-difference scoring protocol. The supplied model must
be a *local* MLX conversion of the reranker, not a general Qwen chat model.
Never called from the web API or used to publish source facts.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from time import perf_counter

from app.services.pair_reranker_trial import (
    INSTRUCTION, _write, reranked_options, reranker_document, reranker_query,
    require_disk_headroom, resume_rows,
)


PREFIX = (
    '<|im_start|>system\nJudge whether the Document meets the requirements '
    'based on the Query and the Instruct provided. Note that the answer can '
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'


def mlx_runtime_limits(*, memory_limit_gb: float = 4.0, cache_limit_mb: float = 128.0) -> dict[str, int]:
    """Bound the process-local allocator policy, not macOS memory or swap.

    MLX documents the memory limit as a guideline, not a hard OS cap. A small
    cache and per-document disk checks are additional safeguards; the measured
    peak must still be inspected before running a larger experiment.
    """
    if not math.isfinite(memory_limit_gb) or memory_limit_gb <= 0:
        raise ValueError("MLX memory limit must be finite and positive.")
    if not math.isfinite(cache_limit_mb) or cache_limit_mb < 0:
        raise ValueError("MLX cache limit must be finite and non-negative.")
    memory_bytes = int(memory_limit_gb * 1024**3)
    cache_bytes = int(cache_limit_mb * 1024**2)
    if cache_bytes > memory_bytes:
        raise ValueError("MLX cache limit must not exceed the memory limit.")
    return {"memory_limit_bytes": memory_bytes, "cache_limit_bytes": cache_bytes}


def select_trial_cases(cases: list[dict], case_id: str | None) -> list[dict]:
    """Optionally restrict an offline diagnostic to one changed case."""
    if case_id is None:
        return cases
    matches = [case for case in cases if case.get("case_id") == case_id]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one captured case named {case_id}.")
    return matches


def final_yes_no_logits(model, mx, token_ids: list[int]):
    """Project only the final hidden state to vocabulary logits.

    The generic model call materializes vocabulary logits for every input
    token. Qwen reranking only reads the final yes/no logits, so projecting
    the final hidden state is mathematically equivalent with far less memory.
    """
    hidden = model.model(mx.array([token_ids]))[:, -1:, :]
    if model.args.tie_word_embeddings:
        logits = model.model.embed_tokens.as_linear(hidden)
    else:
        logits = model.lm_head(hidden)
    return logits[:, -1, :]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--max-cases", type=int, default=50)
    parser.add_argument("--case-id", help="Run one case only for a targeted capture-diff diagnostic")
    parser.add_argument("--resume", action="store_true", help="Continue a matching local checkpoint")
    parser.add_argument("--include-film-title", action="store_true",
                        help="Add the film-scoped title to the reranker query")
    parser.add_argument("--include-pair-context", action="store_true",
                        help="Include both compared film titles in each side's query")
    parser.add_argument("--include-film-context", action="store_true",
                        help="Prefix each passage with its film title and source section")
    parser.add_argument("--instruction", default=INSTRUCTION,
                        help="Override the offline relevance instruction for a controlled trial")
    parser.add_argument("--min-free-gb", type=float, default=6.0)
    parser.add_argument("--memory-limit-gb", type=float, default=4.0,
                        help="Process-local MLX allocation guideline, not a hard OS memory cap")
    parser.add_argument("--cache-limit-mb", type=float, default=128.0)
    parser.add_argument("--verify-logits-equivalence", action="store_true",
                        help="Compare final-token projection with the generic model output once")
    args = parser.parse_args()
    if not 1 <= args.max_cases <= 50:
        raise ValueError("max-cases must be between 1 and 50")
    runtime_limits = mlx_runtime_limits(
        memory_limit_gb=args.memory_limit_gb, cache_limit_mb=args.cache_limit_mb,
    )
    require_disk_headroom(args.output, min_free_gb=args.min_free_gb)
    from mlx_lm import load
    import mlx.core as mx

    mx.set_memory_limit(runtime_limits["memory_limit_bytes"])
    mx.set_cache_limit(runtime_limits["cache_limit_bytes"])
    mx.reset_peak_memory()

    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    if len(capture["cases"]) != 50 or capture["method"] not in {"hybrid", "candidate-union"}:
        raise ValueError("Reranker trial requires a complete hybrid or candidate-union capture.")
    if not args.model.is_dir():
        raise ValueError("The quantized reranker must already exist in a local directory.")
    model, tokenizer = load(str(args.model))
    hf = getattr(tokenizer, "_tokenizer", tokenizer)
    yes_id = hf.convert_tokens_to_ids("yes")
    no_id = hf.convert_tokens_to_ids("no")
    prefix_ids = hf.encode(PREFIX, add_special_tokens=False)
    suffix_ids = hf.encode(SUFFIX, add_special_tokens=False)

    if args.verify_logits_equivalence:
        sample = capture["cases"][0]["first_pool"][0]["content"]
        question = capture["cases"][0]["question"]
        content = f"<Instruct>: {INSTRUCTION}\n<Query>: {question}\n<Document>: {sample}"
        ids = prefix_ids + hf.encode(content, add_special_tokens=False) + suffix_ids
        generic = model(mx.array([ids]))[:, -1, :]
        optimized = final_yes_no_logits(model, mx, ids)
        generic_score = generic[0, yes_id] - generic[0, no_id]
        optimized_score = optimized[0, yes_id] - optimized[0, no_id]
        delta = mx.abs(generic_score - optimized_score)
        mx.eval(delta)
        print(json.dumps({"absolute_yes_no_score_difference": float(delta)}), flush=True)
        if float(delta) > 0.05:
            raise RuntimeError("Final-token yes/no score differs materially from generic model output.")
        return

    def score_pair(question: str, document: str) -> float:
        require_disk_headroom(args.output, min_free_gb=args.min_free_gb)
        content = f"<Instruct>: {args.instruction}\n<Query>: {question}\n<Document>: {document}"
        ids = prefix_ids + hf.encode(content, add_special_tokens=False) + suffix_ids
        if len(ids) > 8192:
            raise ValueError("A question-passage pair exceeds the reranker's 8192-token evaluation cap.")
        logits = final_yes_no_logits(model, mx, ids)
        score = logits[0, yes_id] - logits[0, no_id]
        mx.eval(score)
        result = float(score)
        del logits, score
        mx.clear_cache()
        return result

    instruction = args.instruction + (" Film identity is included in the query." if args.include_film_title else "")
    if args.include_pair_context:
        instruction += " Both compared film titles are included in the query."
    if args.include_film_context:
        instruction += " Each document includes its film title and source section."
    selected_cases = select_trial_cases(capture["cases"], args.case_id)
    rows = resume_rows(args.output, capture_path=args.capture, capture=capture,
                       model_name=str(args.model), instruction=instruction,
                       enabled=args.resume and args.case_id is None)
    for case in selected_cases[len(rows):args.max_cases]:
        require_disk_headroom(args.output, min_free_gb=args.min_free_gb)
        row = {"case_id": case["case_id"], "question": case["question"], "film_qids": case["film_qids"]}
        for side_index, (side, title) in enumerate(zip(("first", "second"), case["titles"], strict=True)):
            pool = case[f"{side}_pool"]
            started = perf_counter()
            other_title = case["titles"][1 - side_index]
            query = reranker_query(
                case["question"],
                title if args.include_film_title or args.include_pair_context else None,
                other_title if args.include_pair_context else None,
            )
            scores = [score_pair(query, reranker_document(
                item["content"],
                film_title=title if args.include_film_context else None,
                section_title=item["section_title"] if args.include_film_context else None,
            )) for item in pool]
            row[f"{side}_ranking"] = reranked_options(pool, scores)
            row[f"{side}_elapsed_ms"] = round((perf_counter() - started) * 1000, 1)
        rows.append(row)
        _write(args.output, {"model": str(args.model), "instruction": instruction,
                             "capture": str(args.capture), "complete": len(rows) == 50,
                             "runtime": {**runtime_limits, "peak_memory_bytes": mx.get_peak_memory()},
                             "cases": rows})
        print(f"{len(rows):02d}/{args.max_cases} {case['case_id']}", flush=True)


if __name__ == "__main__":
    main()
