"""Query a verified local recovery matrix; never changes a serving index."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter

import numpy as np

from app.services.corpus_build_manifest import canonical_digest
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile


def query(reconstructed: dict, mapping: dict, matrix_path: Path, *, question: str,
          film_qids: list[str], ollama_url: str, limit: int = 20) -> dict:
    for item in (reconstructed, mapping):
        if canonical_digest({k: v for k, v in item.items() if k != "fingerprint"}) != item["fingerprint"]:
            raise ValueError("artifact_fingerprint_mismatch")
    if (reconstructed["mapping_fingerprint"] != mapping["fingerprint"]
            or reconstructed["matrix_sha256"] != mapping["matrix_sha256"]
            or reconstructed["model_digest"] != mapping["model_digest"]):
        raise ValueError("mapping_binding_mismatch")
    if not question.strip() or len(set(film_qids)) != 2 or not 1 <= limit <= 50:
        raise ValueError("two_distinct_films_and_question_required")
    with matrix_path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != mapping["matrix_sha256"]:
            raise ValueError("matrix_integrity_failed")
    matrix = np.load(matrix_path, mmap_mode="r", allow_pickle=False)
    rows = reconstructed["rows"]
    if matrix.shape != (len(rows), mapping["dimension"]) or matrix.dtype != np.float32:
        raise ValueError("matrix_shape_mismatch")
    if len(rows) != len(mapping["rows"]) or not np.isfinite(matrix).all():
        raise ValueError("invalid_matrix_or_rows")
    for i, (row, original) in enumerate(zip(rows, mapping["rows"], strict=True)):
        if (row["row"] != i or any(row.get(key) != value for key, value in original.items())
                or hashlib.sha256(row["content"].encode("utf-8")).hexdigest() != row["chunk_sha256"]):
            raise ValueError("reconstructed_row_mismatch")
    if any(not any(row["film_qid"] == qid for row in rows) for qid in film_qids):
        raise ValueError("film_not_in_reconstructed_corpus")
    if (mapping["model"] != "qwen3-embedding:4b" or mapping["dimension"] != 1024
            or not re.fullmatch(r"[0-9a-f]{64}", mapping["model_digest"])):
        raise ValueError("unexpected_model_contract")
    profile = OllamaEmbeddingProfile(model=mapping["model"], dimensions=mapping["dimension"],
                                     expected_model_digest=mapping["model_digest"])
    start = perf_counter()
    vector = np.asarray(OllamaEmbeddingClient(base_url=ollama_url).embed(
        [profile.query_input(question)], profile=profile)[0], dtype=np.float32)
    embedding_seconds = perf_counter() - start
    norms = np.linalg.norm(matrix, axis=1)
    query_norm = np.linalg.norm(vector)
    if vector.shape != (mapping["dimension"],) or not np.isfinite(vector).all() or query_norm == 0 or np.any(norms == 0):
        raise ValueError("invalid_query_or_document_vector")
    similarities = (matrix @ vector) / (norms * query_norm)
    sides = []
    for qid in film_qids:
        indices = [i for i, row in enumerate(rows) if row["film_qid"] == qid]
        if not indices:
            raise ValueError("film_not_in_reconstructed_corpus")
        order = sorted(indices, key=lambda i: (-float(similarities[i]), rows[i]["chunk_id"]))[:limit]
        sides.append({"film_qid": qid, "ranked": [
            {"rank": rank, "score": float(similarities[i]), **rows[i]}
            for rank, i in enumerate(order, 1)]})
    return {"schema": "cinegraph.reconstructed-vector-query/v1", "corpus_fingerprint": reconstructed["fingerprint"],
        "mapping_fingerprint": mapping["fingerprint"], "model_digest": mapping["model_digest"],
        "question": question, "query_embedding_seconds": embedding_seconds, "sides": sides,
        "caution": "Offline exact cosine over a retained development corpus; not a serving index or factual answer."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "mapping", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--film", action="append", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    area = (root / "data" / "evaluation").resolve()
    if any(not path.resolve().is_relative_to(area) for path in (args.corpus, args.mapping, args.output)) or args.output.exists():
        raise ValueError("new_local_evaluation_output_required")
    mapping = json.loads(args.mapping.read_text())
    matrix = (root / mapping["matrix_path"]).resolve()
    if not matrix.is_relative_to(area):
        raise ValueError("matrix_outside_local_evaluation")
    result = query(json.loads(args.corpus.read_text()), mapping, matrix, question=args.question,
                   film_qids=args.film, ollama_url=args.ollama_url)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"films": len(result["sides"]), "embedding_seconds": result["query_embedding_seconds"]}))


if __name__ == "__main__":
    main()
