"""Offline small cross-encoder control on a frozen source-linked candidate pool."""
import argparse
import json
import math
import os
from pathlib import Path
from time import perf_counter

from app.services.rag_dense_trial import digest, source_windows
from app.services.pair_reranker_trial import _write, require_disk_headroom, reranker_query, reranker_document

MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"


def aggregate_windows(pool: list[dict], windows: list[dict], scores: list[float]) -> list[dict]:
    if len(windows) != len(scores) or any(not math.isfinite(score) for score in scores):
        raise ValueError("Every window requires one finite score.")
    allowed = {item["chunk_id"] for item in pool}
    if len(allowed) != len(pool):
        raise ValueError("Candidate IDs must be distinct.")
    winners = {}
    for window, score in zip(windows, scores, strict=True):
        identifier = window["chunk_id"]
        if identifier not in allowed:
            raise ValueError("Window is outside the fixed pool.")
        if identifier not in winners or score > winners[identifier][1]:
            winners[identifier] = (window, score)
    if set(winners) != allowed:
        raise ValueError("Every candidate must have a scored source window.")
    ordered = sorted(enumerate(pool), key=lambda entry: (-winners[entry[1]["chunk_id"]][1], entry[0]))
    return [{"chunk_id": item["chunk_id"], "section_title": item["section_title"],
             "score": winners[item["chunk_id"]][1], "winning_window": winners[item["chunk_id"]][0]}
            for _, item in ordered]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "mps"), default="mps")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    if any(not path.resolve().is_relative_to(root) for path in (args.capture, args.output, args.cache_dir)):
        raise ValueError("All artifacts must remain under project data/evaluation.")
    if args.batch_size < 1:
        raise ValueError("Batch size must be positive.")
    capture = json.loads(args.capture.read_text())
    if capture["method"] != "candidate-union" or not 1 <= len(capture["cases"]) <= 50:
        raise ValueError("Use a frozen pool of one to fifty questions.")
    contract = {"model": MODEL, "revision": REVISION, "device": args.device,
                "input": "film-section-source-window-128w-overlap32-v1", "aggregation": "max-window-logit",
                "batch_size": args.batch_size, "capture_fingerprint": digest(capture)}
    rows = []
    if args.resume and args.output.exists():
        previous = json.loads(args.output.read_text())
        if previous["contract"] != contract:
            raise ValueError("Resume contract differs from the frozen trial.")
        rows = previous["cases"]
        if len(rows) > len(capture["cases"]) or any(
                old["case_id"] != new["case_id"] for old, new in zip(rows, capture["cases"])):
            raise ValueError("Checkpoint is not a prefix of this capture.")
    require_disk_headroom(args.output)
    os.environ["HF_HOME"] = str(args.cache_dir.resolve() / "hf-home")
    os.environ["HF_HUB_OFFLINE"] = "1"
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    if args.device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS unavailable in this runtime.")
    torch.set_num_threads(4)
    started = perf_counter()
    options = dict(revision=REVISION, cache_dir=str(args.cache_dir / "weights"),
                   local_files_only=True, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, **options)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, use_safetensors=True, weights_only=True, **options).to(args.device).eval()
    load_ms = (perf_counter() - started) * 1000
    for case in capture["cases"][len(rows):]:
        require_disk_headroom(args.output)
        row = {"case_id": case["case_id"], "question": case["question"], "film_qids": case["film_qids"]}
        for side, title in zip(("first", "second"), case["titles"], strict=True):
            start = perf_counter()
            pool = case[f"{side}_pool"]
            windows = [{"chunk_id": item["chunk_id"], **span} for item in pool
                       for span in source_windows(item["content"])]
            sections = {item["chunk_id"]: item["section_title"] for item in pool}
            query = reranker_query(case["question"], title)
            scores = []
            for offset in range(0, len(windows), args.batch_size):
                batch = windows[offset:offset + args.batch_size]
                documents = [reranker_document(item["text"], film_title=title,
                             section_title=sections[item["chunk_id"]]) for item in batch]
                encoded = tokenizer([query] * len(batch), documents, padding=True,
                                    truncation=False, return_tensors="pt")
                if encoded["input_ids"].shape[1] > 512:
                    raise ValueError("Cross-encoder input exceeds 512 tokens; no silent truncation.")
                with torch.inference_mode():
                    logits = model(**{key: value.to(args.device) for key, value in encoded.items()}).logits
                    scores.extend(logits.flatten().cpu().tolist())
            row[f"{side}_ranking"] = aggregate_windows(pool, windows, scores)
            row[f"{side}_elapsed_ms"] = (perf_counter() - start) * 1000
            row[f"{side}_window_count"] = len(windows)
        rows.append(row)
        _write(args.output, {"contract": contract, "model_load_ms": load_ms,
                            "complete": len(rows) == len(capture["cases"]), "cases": rows})
        print(f"{len(rows)}/{len(capture['cases'])} {case['case_id']}", flush=True)


if __name__ == "__main__":
    main()
