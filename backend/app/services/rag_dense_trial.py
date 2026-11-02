"""Offline dense model ablations on one frozen source corpus; no DB access."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from time import perf_counter

import numpy as np


def source_windows(content: str, *, words: int = 128, overlap: int = 32) -> list[dict]:
    if words <= 0 or not 0 <= overlap < words:
        raise ValueError("Window size and overlap are invalid.")
    tokens = list(re.finditer(r"\S+", content))
    result = []
    for offset in range(0, len(tokens), words - overlap):
        stop = min(offset + words, len(tokens))
        start_char, end_char = tokens[offset].start(), tokens[stop - 1].end()
        result.append({"start": start_char, "end": end_char, "text": content[start_char:end_char]})
        if stop == len(tokens):
            break
    return result


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":")).encode()).hexdigest()


def pack_parent_context(corpus: dict, ranked: list[dict], *, film_qid: str,
                        character_budget: int = 6000, max_parents: int = 3) -> dict:
    """Expand retrieved anchors to complete source chunks under an explicit budget."""
    if character_budget < 1 or max_parents < 1:
        raise ValueError("Context budgets must be positive.")
    documents = {row["chunk_id"]: row for row in corpus["documents"]}
    selected, omitted, seen = [], [], set()
    used = 0
    for anchor in ranked:
        identifier = anchor["chunk_id"]
        doc = documents.get(identifier)
        if doc is None or doc["film_qid"] != film_qid:
            raise ValueError("Context anchor is outside the selected film/corpus.")
        if identifier in seen:
            continue
        seen.add(identifier)
        length = len(doc["content"])
        if len(selected) >= max_parents or used + length > character_budget:
            omitted.append({"chunk_id": identifier, "reason": "context_budget"})
            continue
        selected.append({"chunk_id": identifier, "start": 0, "end": length,
                         "source_snapshot_id": doc["source_snapshot_id"],
                         "text": doc["content"], "retrieved_anchor": anchor})
        used += length
    return {"parents": selected, "omitted": omitted, "characters": used,
            "character_budget": character_budget, "max_parents": max_parents}


def rank_windows(documents: list[dict], matrix: np.ndarray, query: np.ndarray,
                 *, film_qid: str, limit: int = 10) -> list[dict]:
    if matrix.ndim != 2 or matrix.shape != (len(documents), query.size):
        raise ValueError("Evidence vectors and query dimensions disagree.")
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    if np.any(norms == 0) or not np.all(np.isfinite(norms)):
        raise ValueError("Cannot rank zero or non-finite vectors.")
    scores = (matrix @ query) / norms
    candidates = [i for i, row in enumerate(documents) if row["film_qid"] == film_qid]
    ordered = sorted(candidates, key=lambda i: (-float(scores[i]), documents[i]["window_id"]))
    return [{**documents[i], "score": float(scores[i])} for i in ordered[:limit]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--provider", choices=("ollama", "e5", "bge"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True, help="HF commit SHA or exact local Ollama model digest")
    parser.add_argument("--dimensions", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    allowed = {"ollama": {"qwen3-embedding:0.6b", "qwen3-embedding:4b"},
               "e5": {"intfloat/multilingual-e5-base"}, "bge": {"BAAI/bge-m3"}}
    if args.model not in allowed[args.provider]:
        raise ValueError("Model is not supported by this provider's verified input/pooling contract.")
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    if any(not path.resolve().is_relative_to(root) for path in (args.corpus, args.cache_dir, args.output)):
        raise ValueError("All experiment artifacts must remain under project data/evaluation.")
    if args.batch_size < 1 or args.dimensions < 1:
        raise ValueError("Batch size and dimensions must be positive.")
    corpus = json.loads(args.corpus.read_text())
    expected = corpus.pop("fingerprint")
    if digest(corpus) != expected:
        raise ValueError("Frozen corpus fingerprint failed.")
    contract = {"provider": args.provider, "model": args.model, "revision": args.revision,
                "dimension": args.dimensions, "representation": "source-window-128w-overlap32-v1",
                "pooling": {"ollama": "model-native", "e5": "masked-mean-l2", "bge": "cls-l2"}[args.provider],
                "device": "ollama-managed" if args.provider == "ollama" else args.device,
                "corpus": expected}
    cache = args.cache_dir / digest(contract)
    cache.mkdir(parents=True, exist_ok=True)
    documents = [{"window_id": f"{doc['chunk_id']}:{span['start']}:{span['end']}",
                  "chunk_id": doc["chunk_id"], "film_qid": doc["film_qid"],
                  "source_snapshot_id": doc["source_snapshot_id"], **span,
                  "input": f"Film: {doc['film_title']}\nSection: {doc['section_title']}\nEvidence: {span['text']}"}
                 for doc in corpus["documents"] for span in source_windows(doc["content"])]
    load_start = perf_counter()
    if args.provider == "ollama":
        import httpx
        from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
        tags = httpx.get("http://127.0.0.1:11434/api/tags").json()["models"]
        if not any(row["name"] == args.model and row["digest"] == args.revision for row in tags):
            raise ValueError("Local Ollama model does not match pinned digest.")
        client = OllamaEmbeddingClient(timeout_seconds=300)
        profile = OllamaEmbeddingProfile(model=args.model, dimensions=args.dimensions)
        def embed(values, query=False):
            return client.embed([profile.query_input(v) if query else v for v in values], profile=profile)
    else:
        if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
            raise ValueError("HF model requires an immutable commit SHA.")
        os.environ["HF_HOME"] = str(args.cache_dir.resolve() / "hf-home")
        os.environ["HF_XET_CACHE"] = str(args.cache_dir.resolve() / "hf-home" / "xet")
        os.environ["HF_HUB_DISABLE_XET"] = "1"
        import torch
        from transformers import AutoModel, AutoTokenizer
        if args.device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS was requested but is unavailable in this interpreter.")
        torch.set_num_threads(4)
        model_args = dict(revision=args.revision, cache_dir=str(args.cache_dir / "weights"), trust_remote_code=False)
        tokenizer = AutoTokenizer.from_pretrained(args.model, **model_args)
        # The official pinned BGE-M3 repository ships a PyTorch state dict,
        # not safetensors. Require the restricted weights-only loader.
        model = AutoModel.from_pretrained(args.model, use_safetensors=args.provider == "e5",
                                          weights_only=True, **model_args).to(args.device).eval()
        max_tokens = 512 if args.provider == "e5" else 8192
        def embed(values, query=False):
            prefix = ("query: " if query else "passage: ") if args.provider == "e5" else ""
            batch = tokenizer([prefix + value for value in values], padding=True, truncation=False, return_tensors="pt")
            if batch["input_ids"].shape[1] > max_tokens:
                raise ValueError("Input exceeds model budget; no silent truncation is permitted.")
            batch = {key: value.to(args.device) for key, value in batch.items()}
            with torch.inference_mode():
                hidden = model(**batch).last_hidden_state
                if args.provider == "e5":
                    mask = batch["attention_mask"]
                    pooled = hidden.masked_fill(~mask[..., None].bool(), 0).sum(1) / mask.sum(1)[..., None]
                else:
                    pooled = hidden[:, 0]
                return torch.nn.functional.normalize(pooled, p=2, dim=1).cpu().tolist()
    load_ms = (perf_counter() - load_start) * 1000
    timings = []
    def cached_vectors(values, *, query=False):
        vectors = []
        for offset in range(0, len(values), args.batch_size):
            batch = values[offset:offset + args.batch_size]
            paths = [cache / f"{digest({'query': query, 'text': value})}.json" for value in batch]
            missing = [i for i, path in enumerate(paths) if not path.exists()]
            if missing:
                start = perf_counter()
                generated = embed([batch[i] for i in missing], query=query)
                timings.append({"query": query, "count": len(missing), "ms": (perf_counter() - start) * 1000})
                if len(generated) != len(missing):
                    raise ValueError("Embedding count mismatch.")
                for i, vector in zip(missing, generated, strict=True):
                    array = np.asarray(vector)
                    if array.shape != (args.dimensions,) or not np.isfinite(array).all():
                        raise ValueError("Invalid embedding shape or values.")
                    temporary = paths[i].with_suffix(".tmp")
                    temporary.write_text(json.dumps(vector))
                    temporary.replace(paths[i])
            vectors.extend(json.loads(path.read_text()) for path in paths)
            print(f"{'queries' if query else 'documents'} {min(offset + len(batch), len(values))}/{len(values)}", flush=True)
        return np.asarray(vectors, dtype=np.float32)
    matrix = cached_vectors([row["input"] for row in documents])
    queries = cached_vectors([row["question"] for row in corpus["cases"]], query=True)
    cases = [{**case, "sides": [{"film_qid": qid, "ranked": rank_windows(documents, matrix, vector, film_qid=qid)}
                                for qid in case["film_qids"]]}
             for case, vector in zip(corpus["cases"], queries, strict=True)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"contract": contract, "model_load_ms": load_ms,
                                      "embedding_batches": timings, "cases": cases}, indent=2))


if __name__ == "__main__":
    main()
