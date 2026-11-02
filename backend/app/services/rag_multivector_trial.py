"""Offline BGE-M3 trained token-level late interaction on frozen source windows.

Projection, CLS removal, per-token normalization and mean MaxSim follow the
official FlagEmbedding M3 inference contract; never use a random projection.
https://github.com/FlagOpen/FlagEmbedding/tree/master/FlagEmbedding/inference/embedder/encoder_only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from time import perf_counter

import numpy as np

from app.services.rag_dense_trial import digest, source_windows

REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


def mean_maxsim(query: np.ndarray, passage: np.ndarray) -> float:
    """Reference score for already L2-normalized non-padding token vectors."""
    if (query.ndim != 2 or passage.ndim != 2 or not query.shape[0] or not passage.shape[0]
            or query.shape[1] != passage.shape[1] or not np.isfinite(query).all()
            or not np.isfinite(passage).all()):
        raise ValueError("Nonempty finite token matrices with equal dimensions are required.")
    return float((query @ passage.T).max(axis=1).mean())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "mps"), default="mps")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    if any(not p.resolve().is_relative_to(root) for p in (args.corpus, args.weights, args.output, args.cache_dir)):
        raise ValueError("All experiment files must remain project-local.")
    if args.weights.name != REVISION or args.batch_size < 1:
        raise ValueError("Use the pinned BGE-M3 snapshot and a positive batch size.")
    corpus = json.loads(args.corpus.read_text())
    if digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("Frozen source corpus failed integrity verification.")
    projection_path = args.weights / "colbert_linear.pt"
    if not projection_path.exists():
        raise ValueError("The official trained token projection is mandatory.")
    with projection_path.open("rb") as handle:
        projection_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    contract = {"model": "BAAI/bge-m3", "revision": REVISION,
                "projection_sha256": projection_hash, "corpus": corpus["fingerprint"],
                "representation": "source-window-128w-overlap32-v1",
                "token_contract": "trained-projection-remove-CLS-keep-EOS-L2-mean-MaxSim",
                "inference_dtype": "float32", "cache_dtype": "float32", "device": args.device}
    cache = args.cache_dir / digest(contract)
    cache.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(cache).free < 6 * 1024**3:
        raise ValueError("Keep at least 6 GiB free before the token-vector experiment.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    documents = [{"window_id": f"{d['chunk_id']}:{s['start']}:{s['end']}",
                  "chunk_id": d["chunk_id"], "film_qid": d["film_qid"],
                  "source_snapshot_id": d["source_snapshot_id"], **s,
                  "input": f"Film: {d['film_title']}\nSection: {d['section_title']}\nEvidence: {s['text']}"}
                 for d in corpus["documents"] for s in source_windows(d["content"])]
    os.environ["HF_HUB_OFFLINE"] = "1"
    import torch
    from transformers import AutoModel, AutoTokenizer
    if args.device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("Native Metal is unavailable in this runtime.")
    torch.set_num_threads(4)
    start = perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(args.weights, local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(args.weights, local_files_only=True, trust_remote_code=False,
                                     use_safetensors=False, weights_only=True).to(args.device).eval()
    projection = torch.nn.Linear(model.config.hidden_size, model.config.hidden_size)
    projection.load_state_dict(torch.load(projection_path, map_location="cpu", weights_only=True), strict=True)
    projection = projection.to(args.device).eval()
    load_ms = (perf_counter() - start) * 1000
    timings = []

    def encode(values):
        paths = [cache / f"{digest(v)}.npy" for v in values]
        missing = [i for i, p in enumerate(paths) if not p.exists()]
        for offset in range(0, len(missing), args.batch_size):
            if shutil.disk_usage(cache).free < 6 * 1024**3:
                raise ValueError("Token-vector experiment stopped before exhausting disk headroom.")
            selected = missing[offset:offset + args.batch_size]
            batch = tokenizer([values[i] for i in selected], padding=True, truncation=False, return_tensors="pt")
            if batch["input_ids"].shape[1] > 8192:
                raise ValueError("Input exceeds BGE context; no truncation is allowed.")
            lengths = batch["attention_mask"].sum(1).tolist()
            batch = {key: value.to(args.device) for key, value in batch.items()}
            started = perf_counter()
            with torch.inference_mode():
                hidden = model(**batch).last_hidden_state[:, 1:]
                tokens = torch.nn.functional.normalize(projection(hidden), p=2, dim=-1).cpu().numpy()
            timings.append({"count": len(selected), "ms": (perf_counter() - started) * 1000})
            for i, vectors, length in zip(selected, tokens, lengths, strict=True):
                # Exclude padding and CLS, retain EOS as in official inference.
                temporary = paths[i].with_suffix(".tmp")
                with temporary.open("wb") as handle:
                    np.save(handle, vectors[:length - 1], allow_pickle=False)
                temporary.replace(paths[i])
            print(f"token vectors {min(offset + args.batch_size, len(missing))}/{len(missing)}", flush=True)
        return paths

    def read_tokens(path):
        array = np.load(path, allow_pickle=False)
        if (array.ndim != 2 or array.shape[1] != 1024 or not array.shape[0]
                or not np.isfinite(array).all()
                or not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-4)):
            raise ValueError("Cached BGE token vectors violate their normalized matrix contract.")
        return array

    document_paths = encode([d["input"] for d in documents])
    query_paths = encode([c["question"] for c in corpus["cases"]])
    # Keep token matrices on disk; only one scoring batch is on the accelerator.
    # Unlike a production ANN index, this small-corpus control is exact search.
    del model, projection
    if args.device == "mps":
        torch.mps.empty_cache()
    cases = []
    parity_check = None
    for case, query_path in zip(corpus["cases"], query_paths, strict=True):
        started = perf_counter()
        query_array = read_tokens(query_path)
        q = torch.from_numpy(query_array).to(args.device)
        sides = []
        for qid in case["film_qids"]:
            indices = [i for i, d in enumerate(documents) if d["film_qid"] == qid]
            scores = {}
            for offset in range(0, len(indices), args.batch_size):
                selected = indices[offset:offset + args.batch_size]
                arrays = [read_tokens(document_paths[i]) for i in selected]
                vectors = [torch.from_numpy(array) for array in arrays]
                padded = torch.nn.utils.rnn.pad_sequence(vectors, batch_first=True).to(args.device)
                with torch.inference_mode():
                    matches = torch.einsum("qd,btd->bqt", q, padded)
                    for row, vector in enumerate(vectors):
                        matches[row, :, len(vector):] = -torch.inf
                    result = matches.max(dim=-1).values.mean(dim=-1).cpu().tolist()
                if parity_check is None:
                    reference = mean_maxsim(query_array, arrays[0])
                    error = abs(reference - result[0])
                    if error > 1e-4:
                        raise ValueError("Batched accelerator MaxSim disagrees with the reference score.")
                    parity_check = {"reference": reference, "batched": result[0], "absolute_error": error}
                scores.update(zip(selected, result, strict=True))
            ordered = sorted(indices, key=lambda i: (-scores[i], documents[i]["window_id"]))[:10]
            sides.append({"film_qid": qid, "ranked": [{**documents[i], "score": scores[i]} for i in ordered]})
        cases.append({**case, "sides": sides, "scoring_ms": (perf_counter() - started) * 1000})
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps({"contract": contract, "model_load_ms": load_ms,
            "embedding_batches": timings, "complete": len(cases) == len(corpus["cases"]),
            "scoring_reference_check": parity_check,
            "cases": cases, "cache_bytes": sum(p.stat().st_size for p in set(document_paths + query_paths))}, indent=2))
        temporary.replace(args.output)
        print(f"scored {len(cases)}/{len(corpus['cases'])} {case['case_id']}", flush=True)


if __name__ == "__main__":
    main()
