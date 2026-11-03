"""Produce a local, selection-only disposition for pilot ID crosslinks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.catalog_pilot_manifest import (
    adjudicate_pilot_crosslinks, validate_pilot_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=Path("data/evaluation/catalog-pilot-top100-v5.json"))
    parser.add_argument("--csv", type=Path, default=Path("imdb_top_1000.csv"))
    parser.add_argument("--readiness", type=Path, default=Path("data/evaluation/catalog-readiness-v4.json"))
    parser.add_argument("--imdb-review", type=Path, default=Path("data/evaluation/catalog-pilot-imdb-review-v2.json"))
    parser.add_argument("--identity-evidence", type=Path,
                        default=Path("data/evaluation/catalog-pilot-identity-evidence-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=100)
    args = parser.parse_args()

    root = (Path.cwd() / "data/evaluation").resolve()
    local_inputs = [args.pilot, args.readiness, args.imdb_review, args.identity_evidence]
    if any(not path.resolve().is_relative_to(root) for path in local_inputs):
        raise ValueError("Pilot, readiness, review and identity artifacts must stay in local data/evaluation")
    if args.output.resolve() == args.identity_evidence.resolve():
        raise ValueError("Output must not overwrite the immutable identity evidence artifact")
    if not args.output.resolve().is_relative_to(root) or args.output.exists():
        raise ValueError("Output must be a new file inside local data/evaluation")
    if args.csv.resolve() != (Path.cwd().resolve() / "imdb_top_1000.csv"):
        raise ValueError("Candidate CSV must be the supplied project imdb_top_1000.csv")

    pilot_bytes = args.pilot.read_bytes()
    readiness_bytes = args.readiness.read_bytes()
    review_bytes = args.imdb_review.read_bytes()
    evidence_bytes = args.identity_evidence.read_bytes()
    pilot = json.loads(pilot_bytes)
    review = json.loads(review_bytes)
    evidence = json.loads(evidence_bytes)
    validate_pilot_manifest(pilot, args.csv.read_bytes(), readiness_bytes,
                            review_bytes, expected_count=args.expected_count)
    decisions = adjudicate_pilot_crosslinks(
        pilot, pilot_bytes, review, review_bytes, evidence, evidence_bytes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(decisions, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({"decision_count": decisions["decision_count"],
                      "output": str(args.output), "scope": decisions["scope"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
