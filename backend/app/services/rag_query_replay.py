"""Offline extractive-query ablation over verified cached full-passage vectors.

Reads no database and embeds no documents. All ranking branches retain the
original question; generated facets are search aids, not source assertions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from app.services.embedding_artifacts import document_cache_key
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.lexical_retrieval import Bm25Index
from app.services.rag_dense_trial import digest, rank_windows
from app.services.rag_query_plan import PLANNER_VERSION, parse_queries


def validate_plans(corpus: dict, plans: dict) -> dict[str, list[str]]:
    if digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("Corpus fingerprint failed.")
    if not plans.get("complete") or plans["contract"]["planner_version"] != PLANNER_VERSION:
        raise ValueError("A complete current extractive-plan run is required.")
    rows = plans["cases"]
    if [r["case_id"] for r in rows] != [r["case_id"] for r in corpus["cases"]]:
        raise ValueError("Plans must cover the exact frozen question sequence.")
    result = {}
    for case, plan in zip(corpus["cases"], rows, strict=True):
        if case["question"] != plan["question"] or plan["queries"][0] != case["question"]:
            raise ValueError("Plans must preserve the original question.")
        # Schema failures explicitly fall back to the original query only.
        extras = plan["queries"][1:]
        if extras:
            parse_queries(case["question"], json.dumps({"queries": extras}))
        result[case["case_id"]] = plan["queries"]
    return result


def fuse_branches(branches: list[list[dict]], *, limit: int, policy: str) -> list[dict]:
    """Deterministic RRF or round-robin diversification, without source duplication."""
    if not branches or limit < 1 or policy not in {"rrf", "round-robin", "original"}:
        raise ValueError("Invalid ranking policy or budget.")
    if policy == "original":
        return branches[0][:limit]
    items, scores, order = {}, {}, []
    for branch in branches:
        if len({r["chunk_id"] for r in branch}) != len(branch):
            raise ValueError("A ranking branch must not repeat source chunks.")
        for rank, row in enumerate(branch, 1):
            key = row["chunk_id"]
            items.setdefault(key, row)
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
    if policy == "rrf":
        order = sorted(items, key=lambda key: (-scores[key], key))
    else:
        seen = set()
        for rank in range(max(map(len, branches))):
            for branch in branches:
                if rank < len(branch) and branch[rank]["chunk_id"] not in seen:
                    key = branch[rank]["chunk_id"]
                    seen.add(key)
                    order.append(key)
    return [{**items[key], "fusion_score": scores[key]} for key in order[:limit]]


def load_documents(corpus: dict, vector_path: Path, *, profile: OllamaEmbeddingProfile,
                   chunker_version: str) -> tuple[list[dict], np.ndarray]:
    docs = corpus["documents"]
    if [r["chunk_id"] for r in docs] != sorted(r["chunk_id"] for r in docs):
        raise ValueError("Cached matrix requires canonical chunk ordering.")
    inputs = [f"Film: {d['film_title']}\nSection: {d['section_title']}\nEvidence: {d['content']}" for d in docs]
    key = document_cache_key(provider="ollama", model_name=profile.model, dimensions=profile.dimensions,
                             chunk_run_id=corpus["chunk_run_id"], chunker_version=chunker_version,
                             contents=inputs)
    expected = f"{profile.model.replace('/', '--').replace(':', '--')}-{key}.npy"
    if vector_path.name != expected:
        raise ValueError("Vector cache identity does not match exact corpus and model contract.")
    matrix = np.load(vector_path, allow_pickle=False)
    if matrix.shape != (len(docs), profile.dimensions) or not np.isfinite(matrix).all():
        raise ValueError("Invalid cached matrix shape or values.")
    return [{**d, "window_id": d["chunk_id"], "start": 0, "end": len(d["content"]),
             "text": d["content"]} for d in docs], matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("plans", type=Path)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--chunker-version", required=True)
    parser.add_argument("--model", default="qwen3-embedding:4b")
    parser.add_argument("--dimensions", type=int, default=2560)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    if any(not p.resolve().is_relative_to(root) for p in
           (args.corpus, args.plans, args.vectors, args.output)):
        raise ValueError("Experiment files must stay under project data/evaluation.")
    corpus, plans = json.loads(args.corpus.read_text()), json.loads(args.plans.read_text())
    queries = validate_plans(corpus, plans)
    profile = OllamaEmbeddingProfile(model=args.model, dimensions=args.dimensions)
    documents, matrix = load_documents(corpus, args.vectors, profile=profile, chunker_version=args.chunker_version)
    import httpx
    models = httpx.get("http://127.0.0.1:11434/api/tags").json()["models"]
    if not any(r["name"] == args.model and r["digest"] == args.revision for r in models):
        raise ValueError("Ollama model digest differs from experiment contract.")
    client = OllamaEmbeddingClient(timeout_seconds=300)
    outputs = {policy: [] for policy in ("original", "rrf", "round-robin", "bm25", "hybrid")}
    timings = []
    cache = args.output.parent / "query-replay-cache" / digest({"model": args.model,
        "revision": args.revision, "dimensions": args.dimensions, "instruction": profile.query_instruction})
    cache.mkdir(parents=True, exist_ok=True)
    for case in corpus["cases"]:
        start = perf_counter()
        sides = {policy: [] for policy in outputs}
        for qid in case["film_qids"]:
            title = next(d["film_title"] for d in documents if d["film_qid"] == qid)
            branches = []
            for query in queries[case["case_id"]]:
                value = profile.query_input(f"Film: {title}\nResearch question: {query}")
                path = cache / f"{digest(value)}.json"
                if not path.exists():
                    vector = client.embed([value], profile=profile)[0]
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(vector))
                    temporary.replace(path)
                vector = np.asarray(json.loads(path.read_text()), dtype=np.float32)
                if vector.shape != (profile.dimensions,) or not np.isfinite(vector).all():
                    raise ValueError("Invalid cached query vector.")
                branches.append(rank_windows(documents, matrix, vector, film_qid=qid, limit=30))
            for policy in ("original", "rrf", "round-robin"):
                sides[policy].append({"film_qid": qid, "ranked": fuse_branches(branches, limit=10, policy=policy)})
            film_docs = [d for d in documents if d["film_qid"] == qid]
            lexical = Bm25Index.build(d["content"] for d in film_docs)
            scores = lexical.scores(case["question"])
            lexical_ranked = [{**film_docs[i], "score": scores[i]} for i in
                              lexical.rank(case["question"], cutoff=30) if scores[i] > 0]
            sides["bm25"].append({"film_qid": qid, "ranked": lexical_ranked[:10]})
            sides["hybrid"].append({"film_qid": qid, "ranked": fuse_branches(
                [branches[0], lexical_ranked], limit=10, policy="rrf")})
        timings.append({"case_id": case["case_id"], "ms": (perf_counter() - start) * 1000})
        for policy in outputs:
            outputs[policy].append({**case, "sides": sides[policy]})
        print(f"{len(timings)}/{len(corpus['cases'])} {case['case_id']}", flush=True)
    with args.vectors.open("rb") as handle:
        matrix_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    args.output.write_text(json.dumps({"corpus_fingerprint": corpus["fingerprint"],
        "plan_fingerprint": digest(plans), "vector_sha256": matrix_hash,
        "model": args.model, "revision": args.revision, "dimensions": args.dimensions,
        "branch_limit": 30, "output_limit": 10, "rrf_constant": 60,
        "lexical_contract": "existing-Bm25Index-k1=1.5-b=0.75-film-scoped-original-query",
        "policies": outputs, "timings": timings,
        "caution": "Development source visibility ablation, not validated answer quality."}, indent=2))


if __name__ == "__main__":
    main()
