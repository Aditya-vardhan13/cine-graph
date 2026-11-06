"""Freeze and validate an English-first local pilot from the existing catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.english_catalog_pilot import (
    build_english_catalog_pilot,
    validate_english_catalog_pilot,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=100)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    if args.csv.resolve() != (project / "imdb_top_1000.csv").resolve():
        raise ValueError("Candidate list must be the supplied local imdb_top_1000.csv")
    if not args.readiness.resolve().is_relative_to(evaluation):
        raise ValueError("Readiness artifact must be under local data/evaluation")
    if not args.output.resolve().is_relative_to(evaluation):
        raise ValueError("Pilot output must be under local data/evaluation")

    csv_bytes = args.csv.read_bytes()
    readiness_bytes = args.readiness.read_bytes()
    if args.validate:
        pilot = json.loads(args.output.read_text(encoding="utf-8"))
        result = validate_english_catalog_pilot(
            pilot, csv_bytes, readiness_bytes, expected_count=args.expected_count,
        )
        print(json.dumps(result, indent=2))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    pilot = build_english_catalog_pilot(
        csv_bytes, readiness_bytes, expected_count=args.expected_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(pilot, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({
        "film_count": pilot["film_count"],
        "input_rows_scanned": pilot["input_rows_scanned"],
        "skipped_input_rows_before_completion": pilot["skipped_input_rows_before_completion"],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
