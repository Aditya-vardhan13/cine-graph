"""Development-only whole-story embedding control; never evaluates held-out cases."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.pair_reranker_trial import require_disk_headroom

MODEL = "qwen3-embedding:0.6b"
DIGEST = "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d"


def cosine(a, b):
    if len(a) != len(b) or not a:
        raise ValueError("Embedding dimensions disagree.")
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("Invalid vector norm.")
    return sum(x*y for x, y in zip(a, b, strict=True)) / norm


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prepared", type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    local = (ROOT / "data/evaluation").resolve()
    if not local.is_relative_to(ROOT.resolve()) or any(not path.resolve().is_relative_to(local) for path in (args.prepared, args.output)):
        raise ValueError("Experiment files must stay in project evaluation storage.")
    report = json.loads((args.prepared / "report.json").read_text())
    def read(name, *, development_only=False):
        raw = (args.prepared / f"{name}.jsonl").read_bytes()
        if hashlib.sha256(raw).hexdigest() != report["outputs"][name]["sha256"]:
            raise ValueError(f"Prepared {name} fingerprint mismatch.")
        lines = raw.splitlines()
        if development_only:
            lines = [line for line in lines if b'"case_id": "semeval:dev:' in line]
        return [json.loads(line) for line in lines]
    questions = read("evaluation-prompts", development_only=True)
    ids = {v for q in questions for v in q["stories"].values()}
    documents = {d["document_id"]: d for d in read("evidence-documents") if d["document_id"] in ids}
    if len(questions) != 200 or set(documents) != ids:
        raise ValueError("Development scope or source coverage changed.")
    if not any(m["name"] == MODEL and m["digest"] == DIGEST for m in httpx.get("http://127.0.0.1:11435/api/tags", timeout=5).json()["models"]):
        raise ValueError("Local model digest mismatch.")
    args.output.mkdir(parents=True, exist_ok=False)
    profile = OllamaEmbeddingProfile(model=MODEL, dimensions=1024)
    client = OllamaEmbeddingClient(base_url="http://127.0.0.1:11435", timeout_seconds=180)
    vectors = {}
    started = perf_counter()
    cache = args.output / "vectors.jsonl"
    with cache.open("x") as f:
        ordered = sorted(ids)
        for offset in range(0, len(ordered), 4):
            require_disk_headroom(args.output)
            batch = ordered[offset:offset + 4]
            result = client.embed([documents[key]["content"] for key in batch], profile=profile)
            for key, vector in zip(batch, result, strict=True):
                if not all(math.isfinite(v) for v in vector):
                    raise ValueError("Non-finite embedding.")
                vectors[key] = vector
                f.write(json.dumps({"document_id": key, "vector": vector}) + "\n")
            f.flush()
            print(f"embedded {min(offset + len(batch), len(ordered))}/{len(ordered)}", flush=True)
    predictions = []
    for q in questions:
        s = q["stories"]
        a, b = cosine(vectors[s["anchor"]], vectors[s["a"]]), cosine(vectors[s["anchor"]], vectors[s["b"]])
        predictions.append({"case_id": q["case_id"], "score_a": a, "score_b": b, "a_is_closer": None if a == b else a > b})
    (args.output / "predictions.json").write_text(json.dumps(predictions, indent=2))
    # Open gold only after all predictions have been fixed and saved.
    gold = {r["case_id"]: r for r in read("gold-labels", development_only=True)}
    if set(gold) != {r["case_id"] for r in predictions}:
        raise ValueError("Development labels and predictions disagree.")
    correct = sum(r["a_is_closer"] == gold[r["case_id"]]["a_is_closer"] for r in predictions)
    result = {"version": "semeval-qwen-0.6b-dev-v1", "model": MODEL, "digest": DIGEST,
              "quantization": "Q8_0", "representation": "whole-story symmetric cosine; no query instruction",
              "development_cases": len(predictions), "stories": len(ids), "correct": correct,
              "ties": sum(r["a_is_closer"] is None for r in predictions), "seconds": perf_counter() - started,
              "heldout_evaluated": False,
              "caution": "Development triplet similarity only; not film retrieval or writing quality."}
    (args.output / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
