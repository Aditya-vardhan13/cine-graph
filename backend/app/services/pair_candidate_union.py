"""Build an offline candidate-pool union from frozen retrieval captures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.pair_relevance_eval import merge_candidate_captures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.captures) < 2:
        parser.error("provide at least two retrieval captures")
    captures = [json.loads(path.read_text(encoding="utf-8")) for path in args.captures]
    union = merge_candidate_captures(*captures)
    union["source_captures"] = [str(path) for path in args.captures]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(union, indent=2), encoding="utf-8")
    pool_sizes = [
        len(case["first_pool"]) + len(case["second_pool"])
        for case in union["cases"]
    ]
    print(json.dumps({
        "output": str(args.output), "cases": len(union["cases"]),
        "source_methods": union["source_methods"],
        "candidate_count": sum(pool_sizes),
        "candidate_count_min_per_question": min(pool_sizes),
        "candidate_count_max_per_question": max(pool_sizes),
    }, indent=2))


if __name__ == "__main__":
    main()
