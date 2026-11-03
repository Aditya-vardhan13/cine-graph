"""Development-only whole-story embedding control; never evaluates held-out cases."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.pair_reranker_trial import require_disk_headroom

MODEL = "qwen3-embedding:0.6b"
DIGEST = "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d"
BGE_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


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
    p.add_argument("--provider", choices=("qwen", "bge"), default="qwen")
    p.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    p.add_argument("--holdout-manifest", type=Path, help="Evaluate only the already-frozen disjoint test IDs.")
    args = p.parse_args()
    local = (ROOT / "data/evaluation").resolve()
    paths = [args.prepared, args.output] + ([args.holdout_manifest] if args.holdout_manifest else [])
    if not local.is_relative_to(ROOT.resolve()) or any(not path.resolve().is_relative_to(local) for path in paths):
        raise ValueError("Experiment files must stay in project evaluation storage.")
    report = json.loads((args.prepared / "report.json").read_text())
    def read(name, *, case_prefix=None, case_ids=None):
        raw = (args.prepared / f"{name}.jsonl").read_bytes()
        if hashlib.sha256(raw).hexdigest() != report["outputs"][name]["sha256"]:
            raise ValueError(f"Prepared {name} fingerprint mismatch.")
        lines = raw.splitlines()
        if case_prefix:
            prefix = ('"case_id": "' + case_prefix).encode()
            lines = [line for line in lines if prefix in line]
        if case_ids is not None:
            # Restrict before JSON parsing so unused held-out labels stay unseen.
            lines = [line for line in lines if (match := re.search(rb'"case_id": "([^"\\]+)"', line))
                     and match.group(1).decode() in case_ids]
        return [json.loads(line) for line in lines]
    frozen = None
    if args.holdout_manifest:
        frozen = json.loads(args.holdout_manifest.read_text())
        actual = hashlib.sha256((args.prepared / "report.json").read_bytes()).hexdigest()
        if frozen["prepared_report_sha256"] != actual or frozen["gold_opened"] is not False:
            raise ValueError("Frozen holdout manifest does not match the prepared corpus.")
        allowed_ids = set(frozen["case_ids"])
        if len(allowed_ids) != len(frozen["case_ids"]) or not allowed_ids:
            raise ValueError("Invalid frozen holdout IDs.")
        questions = [q for q in read("evaluation-prompts", case_prefix="semeval:test:") if q["case_id"] in allowed_ids]
        if {q["case_id"] for q in questions} != allowed_ids or any(q["source_identity_disjoint_from_dev_and_sample"] is not True for q in questions):
            raise ValueError("Frozen cases are missing or not source-identity-disjoint.")
    else:
        questions = read("evaluation-prompts", case_prefix="semeval:dev:")
    ids = {v for q in questions for v in q["stories"].values()}
    documents = {d["document_id"]: d for d in read("evidence-documents") if d["document_id"] in ids}
    if (frozen is None and len(questions) != 200) or set(documents) != ids:
        raise ValueError("Development scope or source coverage changed.")
    if args.provider == "qwen":
        import httpx
        if not any(m["name"] == MODEL and m["digest"] == DIGEST for m in httpx.get("http://127.0.0.1:11435/api/tags", timeout=5).json()["models"]):
            raise ValueError("Local model digest mismatch.")
    require_disk_headroom(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    if args.provider == "qwen":
        from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
        profile = OllamaEmbeddingProfile(model=MODEL, dimensions=1024)
        client = OllamaEmbeddingClient(base_url="http://127.0.0.1:11435", timeout_seconds=180)
        def embed(texts):
            return client.embed(texts, profile=profile)
        batch_size = 4
    else:
        os.environ["HF_HOME"] = str(ROOT / "data/evaluation/rag-v2/encoders/hf-home")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from transformers import AutoModel, AutoTokenizer
        if args.device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("Requested MPS device is unavailable.")
        torch.set_num_threads(4)
        opts = {"revision": BGE_REVISION, "cache_dir": str(ROOT / "data/evaluation/rag-v2/encoders/weights"),
                "local_files_only": True, "trust_remote_code": False}
        tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3", **opts)
        model = AutoModel.from_pretrained("BAAI/bge-m3", weights_only=True, use_safetensors=False, **opts).to(args.device).eval()
        def embed(texts):
            batch = tokenizer(texts, padding=True, truncation=False, return_tensors="pt")
            if batch["input_ids"].shape[1] > 8192:
                raise ValueError("Story exceeds BGE's context; truncation is not permitted.")
            with torch.inference_mode():
                out = model(**{key: val.to(args.device) for key, val in batch.items()}).last_hidden_state[:, 0]
                return torch.nn.functional.normalize(out, p=2, dim=1).cpu().tolist()
        batch_size = 1
    vectors = {}
    started = perf_counter()
    cache = args.output / "vectors.jsonl"
    with cache.open("x") as f:
        ordered = sorted(ids)
        for offset in range(0, len(ordered), batch_size):
            require_disk_headroom(args.output)
            batch = ordered[offset:offset + batch_size]
            result = embed([documents[key]["content"] for key in batch])
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
    prediction_ids = {p["case_id"] for p in predictions}
    gold = {r["case_id"]: r for r in read("gold-labels", case_prefix="semeval:test:" if frozen else "semeval:dev:",
                                         case_ids=prediction_ids)}
    if set(gold) != {r["case_id"] for r in predictions}:
        raise ValueError("Development labels and predictions disagree.")
    correct = sum(r["a_is_closer"] == gold[r["case_id"]]["a_is_closer"] for r in predictions)
    result = {"version": "semeval-whole-story-v2", "model": MODEL if args.provider == "qwen" else "BAAI/bge-m3",
              "digest": DIGEST if args.provider == "qwen" else BGE_REVISION,
              "quantization": "Q8_0" if args.provider == "qwen" else "float32",
              "device": "ollama-managed" if args.provider == "qwen" else args.device,
              "representation": "whole-story symmetric cosine; no query instruction",
              "split": "frozen-source-identity-disjoint-test" if frozen else "development",
              "cases": len(predictions), "stories": len(ids), "correct": correct,
              "ties": sum(r["a_is_closer"] is None for r in predictions), "seconds": perf_counter() - started,
              "heldout_evaluated": frozen is not None,
              "frozen_manifest_sha256": hashlib.sha256(args.holdout_manifest.read_bytes()).hexdigest() if frozen else None,
              "caution": "Triplet story similarity only; not film retrieval or writing quality. Pretraining exposure unknown."}
    (args.output / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
