"""Freeze/validate a title-and-year-only English catalog target artifact locally."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.english_catalog_target import (
    build_english_catalog_target,
    validate_english_catalog_target,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("imdb_top_1000.csv"))
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/evaluation/catalog-target-english1000-candidates-v1.json"),
    )
    parser.add_argument("--expected-count", type=int, default=1000)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    if args.csv.resolve() != (project / "imdb_top_1000.csv").resolve():
        raise ValueError("Candidate CSV must be the supplied project imdb_top_1000.csv")
    if not args.output.resolve().is_relative_to(evaluation):
        raise ValueError("Candidate manifest must stay under local data/evaluation")
    csv_bytes = args.csv.read_bytes()
    if args.validate:
        manifest = json.loads(args.output.read_text(encoding="utf-8"))
        result = validate_english_catalog_target(
            manifest, csv_bytes, expected_count=args.expected_count,
        )
        print(json.dumps(result, indent=2))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = build_english_catalog_target(csv_bytes, expected_count=args.expected_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({
        "candidate_count": manifest["candidate_count"],
        "input_row_count": manifest["input_row_count"],
        "out_of_scope_rows_after_selection": manifest["out_of_scope_rows_after_selection"],
        "input_sha256": manifest["input_sha256"],
        "output": str(args.output),
        "catalog_identity_resolved": manifest["catalog_identity_resolved"],
    }, indent=2))


if __name__ == "__main__":
    main()
