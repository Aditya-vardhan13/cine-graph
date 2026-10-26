"""Offline cross-encoder trial on a frozen, source-linked pair retrieval capture.

Run outside the API process. The input and output stay under ignored local
data/evaluation; model weights are never committed. Scores are *rankings*, not
relevance judgments. A separate reviewed label file is needed for metrics.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from time import perf_counter


INSTRUCTION = (
    "Given a film research question, rank passages that directly address the "
    "specific conflict, choice, craft, or interpretation asked about. A passage "
    "about the same film or broad topic is not enough."
)


def reranker_query(question: str, film_title: str | None = None,
                   comparison_film_title: str | None = None) -> str:
    """Add the film identity that is implicit in the retrieval scope.

    Candidate passages are already film-scoped, but the reranker previously
    saw only the pair question. Including the scoped title tests whether an
    explicit subject improves passage relevance without changing the source
    pool or the question itself.
    """
    if not film_title and not comparison_film_title:
        return question
    lines = []
    if film_title:
        lines.append(f"Film: {film_title}")
    if comparison_film_title:
        lines.append(f"Comparison film: {comparison_film_title}")
    lines.append(f"Research question: {question}")
    return "\n".join(lines)


def reranker_document(content: str, *, film_title: str | None = None,
                      section_title: str | None = None) -> str:
    """Add explicit film and source-section context without altering evidence."""
    if not film_title and not section_title:
        return content
    lines = []
    if film_title:
        lines.append(f"Film: {film_title}")
    if section_title:
        lines.append(f"Section: {section_title}")
    return "\n".join([*lines, f"Evidence: {content}"])


def reranked_options(pool: list[dict], scores: list[float]) -> list[dict]:
    if len(pool) != len(scores):
        raise ValueError("A score is required for every candidate passage.")
    return [
        {"chunk_id": pool[index]["chunk_id"], "score": round(float(scores[index]), 6),
         "section_title": pool[index]["section_title"]}
        for index in sorted(range(len(pool)), key=lambda index: (-scores[index], index))
    ]


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def resume_rows(
    path: Path, *, capture_path: Path, capture: dict, model_name: str,
    instruction: str, enabled: bool,
) -> list[dict]:
    """Resume only an exact, prefix-complete trial; never mix candidate sets."""
    if not enabled or not path.exists():
        return []
    previous = json.loads(path.read_text(encoding="utf-8"))
    if (previous.get("capture") != str(capture_path)
            or previous.get("model") != model_name
            or previous.get("instruction") != instruction):
        raise ValueError("Existing reranker checkpoint belongs to a different trial.")
    rows = previous.get("cases", [])
    if len(rows) > len(capture["cases"]):
        raise ValueError("Existing reranker checkpoint exceeds the captured case count.")
    for completed, case in zip(rows, capture["cases"], strict=False):
        if (completed["case_id"] != case["case_id"]
                or completed["question"] != case["question"]
                or completed["film_qids"] != case["film_qids"]):
            raise ValueError("Existing reranker checkpoint does not match captured questions.")
        for side in ("first", "second"):
            expected = {item["chunk_id"] for item in case[f"{side}_pool"]}
            actual = {item["chunk_id"] for item in completed[f"{side}_ranking"]}
            if expected != actual or len(expected) != len(completed[f"{side}_ranking"]):
                raise ValueError("Existing reranker checkpoint has a different candidate pool.")
    return rows


def require_disk_headroom(path: Path, *, min_free_gb: float = 6.0) -> None:
    """Stop a local model trial before macOS swap can fill the workspace disk."""
    if min_free_gb < 0:
        raise ValueError("Minimum free disk space cannot be negative.")
    available = shutil.disk_usage(path.parent if path.parent.exists() else Path.cwd()).free
    if available < min_free_gb * 1024**3:
        raise RuntimeError(
            f"Only {available / 1024**3:.1f} GiB free; need {min_free_gb:.1f} GiB "
            "before continuing the local reranker trial."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-Reranker-0.6B")
    parser.add_argument("--max-cases", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--resume", action="store_true", help="Continue a matching local checkpoint")
    parser.add_argument("--include-film-title", action="store_true",
                        help="Add the current film title to each query")
    parser.add_argument("--include-film-context", action="store_true",
                        help="Prefix each passage with its film title and Wikipedia section")
    parser.add_argument("--use-instruction", action=argparse.BooleanOptionalAction, default=True,
                        help="Apply the Qwen-trained relevance instruction prompt")
    parser.add_argument("--min-free-gb", type=float, default=6.0)
    args = parser.parse_args()
    if not 1 <= args.max_cases <= 50:
        raise ValueError("max-cases must be between 1 and 50")
    require_disk_headroom(args.output, min_free_gb=args.min_free_gb)
    from sentence_transformers import CrossEncoder

    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    if len(capture["cases"]) != 50 or capture["method"] not in {"hybrid", "candidate-union"}:
        raise ValueError("Reranker trial requires a complete hybrid or candidate-union capture.")
    model = CrossEncoder(
        args.model,
        **({"prompts": {"cinegraph": INSTRUCTION}, "default_prompt_name": "cinegraph"}
           if args.use_instruction else {}),
    )
    instruction = (INSTRUCTION if args.use_instruction else "none") + (
        " Each document includes its film title and source section."
        if args.include_film_context else ""
    )
    if args.include_film_title:
        instruction += " Each query includes its film title."
    rows = resume_rows(args.output, capture_path=args.capture, capture=capture,
                       model_name=args.model, instruction=instruction, enabled=args.resume)
    for case in capture["cases"][len(rows):args.max_cases]:
        require_disk_headroom(args.output, min_free_gb=args.min_free_gb)
        row = {"case_id": case["case_id"], "question": case["question"], "film_qids": case["film_qids"]}
        for side, title in zip(("first", "second"), case["titles"], strict=True):
            pool = case[f"{side}_pool"]
            started = perf_counter()
            query = reranker_query(case["question"], title if args.include_film_title else None)
            pairs = [(query, reranker_document(
                item["content"],
                film_title=title if args.include_film_context else None,
                section_title=item["section_title"] if args.include_film_context else None,
            )) for item in pool]
            scores = model.predict(pairs, batch_size=args.batch_size, show_progress_bar=False).tolist() if pairs else []
            row[f"{side}_ranking"] = reranked_options(pool, scores)
            row[f"{side}_elapsed_ms"] = round((perf_counter() - started) * 1000, 1)
        rows.append(row)
        _write(args.output, {"model": args.model, "instruction": instruction,
                             "capture": str(args.capture), "complete": len(rows) == 50,
                             "cases": rows})
        print(f"{len(rows):02d}/{args.max_cases} {case['case_id']}", flush=True)


if __name__ == "__main__":
    main()
