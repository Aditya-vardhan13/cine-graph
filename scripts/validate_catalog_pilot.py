"""Validate the frozen local catalog pilot against its hashed input artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.catalog_pilot_manifest import validate_pilot_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("csv", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("--imdb-review", type=Path)
    parser.add_argument("--expected-count", type=int, default=100)
    args = parser.parse_args()

    evaluation = (Path.cwd() / "data/evaluation").resolve()
    inputs = [args.pilot, args.readiness] + ([args.imdb_review] if args.imdb_review else [])
    if any(not path.resolve().is_relative_to(evaluation) for path in inputs):
        raise ValueError("Pilot, readiness and review artifacts must stay in local data/evaluation")
    expected_csv = Path.cwd().resolve() / "imdb_top_1000.csv"
    if args.csv.resolve() != expected_csv:
        raise ValueError("Candidate CSV must be the supplied project imdb_top_1000.csv")

    pilot = json.loads(args.pilot.read_text(encoding="utf-8"))
    summary = validate_pilot_manifest(
        pilot,
        args.csv.read_bytes(),
        args.readiness.read_bytes(),
        args.imdb_review.read_bytes() if args.imdb_review else None,
        expected_count=args.expected_count,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
