"""Bind a saved local vector query to exact chunks for an offline draft."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.corpus_build_manifest import canonical_digest


def prepare(corpus: dict, query: dict, *, depth: int = 5) -> dict:
    if not 1 <= depth <= 20:
        raise ValueError("candidate_depth_out_of_bounds")
    if canonical_digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    if (query["corpus_fingerprint"] != corpus["fingerprint"] or len(query["sides"]) != 2
            or len({side["film_qid"] for side in query["sides"]}) != 2):
        raise ValueError("query_scope_mismatch")
    chunks = {row["chunk_id"]: row for row in corpus["rows"]}
    if len(chunks) != len(corpus["rows"]):
        raise ValueError("duplicate_chunk")
    sides = []
    for side in query["sides"]:
        selected = []
        for candidate in side["ranked"][:depth]:
            row = chunks[candidate["chunk_id"]]
            if (row["film_qid"] != side["film_qid"] or row != {k: candidate[k] for k in row}
                    or hashlib.sha256(row["content"].encode("utf-8")).hexdigest() != row["chunk_sha256"]):
                raise ValueError("candidate_source_mismatch")
            selected.append({"chunk_id": row["chunk_id"], "film_qid": row["film_qid"],
                "source_snapshot_id": row["snapshot_id"], "section_title": row["section_title"],
                "text": row["content"], "start": 0, "end": len(row["content"])})
        if not selected:
            raise ValueError("missing_film_evidence")
        sides.append({"film_qid": side["film_qid"], "selected": selected})
    return {"schema": "cinegraph.reconstructed-draft-packet/v1", "corpus_fingerprint": corpus["fingerprint"], "candidate_depth": depth,
        "query_sha256": canonical_digest(query), "cases": [{"question": query["question"], "sides": sides}],
        "caution": "Unreviewed retrieved leads for an offline development draft, not evidence of answer correctness."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "query", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--depth", type=int, default=5)
    args = parser.parse_args()
    area = (Path.cwd() / "data" / "evaluation").resolve()
    if any(not path.resolve().is_relative_to(area) for path in (args.corpus, args.query, args.output)) or args.output.exists():
        raise ValueError("new_local_evaluation_output_required")
    result = prepare(json.loads(args.corpus.read_text()), json.loads(args.query.read_text()), depth=args.depth)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"films": len(result["cases"][0]["sides"]), "query_sha256": result["query_sha256"]}))


if __name__ == "__main__":
    main()
