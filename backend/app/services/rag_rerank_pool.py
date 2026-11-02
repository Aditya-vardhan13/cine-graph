"""Bind a captured dense candidate pool to frozen source text before reranking."""
import argparse
import json
from pathlib import Path

from app.services.rag_dense_trial import digest


def prepare_pool(corpus: dict, trial: dict, *, limit: int = 10) -> dict:
    if not 1 <= limit <= 50:
        raise ValueError("Pool limit must be between one and fifty.")
    if digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("Frozen corpus fingerprint failed.")
    documents = {row["chunk_id"]: row for row in corpus["documents"]}
    questions = {row["case_id"]: row for row in corpus["cases"]}
    if len(trial["cases"]) != len(questions) or {row["case_id"] for row in trial["cases"]} != set(questions):
        raise ValueError("Capture must include each frozen question exactly once.")
    cases = []
    for row in trial["cases"]:
        question = questions[row["case_id"]]
        if row["question"] != question["question"] or row["film_qids"] != question["film_qids"]:
            raise ValueError("Capture question or film identity drifted.")
        prepared = {"case_id": row["case_id"], "question": row["question"],
                    "film_qids": row["film_qids"], "titles": row["titles"]}
        for side, qid in zip(("first", "second"), row["film_qids"], strict=True):
            pool = row[f"{side}_pool"][:limit]
            if not pool or len({item["chunk_id"] for item in pool}) != len(pool):
                raise ValueError("Each side requires a nonempty distinct source pool.")
            for item in pool:
                doc = documents.get(item["chunk_id"])
                if (doc is None or doc["film_qid"] != qid or item["content"] != doc["content"] or
                        item["source_snapshot_id"] != doc["source_snapshot_id"]):
                    raise ValueError("Candidate content or source identity differs from frozen corpus.")
            prepared[f"{side}_pool"] = pool
        cases.append(prepared)
    return {"method": "candidate-union", "pool_policy": "single-capture-fixed-pool-v1",
            "corpus_fingerprint": corpus["fingerprint"], "limit_per_film": limit, "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    if any(not p.resolve().is_relative_to(root) for p in (args.corpus, args.trial, args.output)):
        raise ValueError("Reranker artifacts must remain under project data/evaluation.")
    result = prepare_pool(json.loads(args.corpus.read_text()), json.loads(args.trial.read_text()), limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({"cases": len(result["cases"]), "fingerprint": digest(result)}))


if __name__ == "__main__":
    main()
