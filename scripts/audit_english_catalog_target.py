"""Create a read-only exact title/year candidate join for the frozen 1,000."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.english_catalog_target import validate_english_catalog_target
from app.services.english_catalog_target_resolution import resolve_english_catalog_target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("imdb_top_1000.csv"))
    parser.add_argument(
        "--target", type=Path,
        default=Path("data/evaluation/catalog-target-english1000-candidates-v1.json"),
    )
    parser.add_argument(
        "--readiness", type=Path, default=Path("data/evaluation/catalog-readiness-v7.json"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/evaluation/catalog-target-english1000-identity-audit-v1.json"),
    )
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    if args.csv.resolve() != (project / "imdb_top_1000.csv").resolve():
        raise ValueError("Candidate CSV must be the supplied project imdb_top_1000.csv")
    if any(not path.resolve().is_relative_to(evaluation) for path in (args.target, args.readiness, args.output)):
        raise ValueError("Target, readiness and audit artifacts must stay in local data/evaluation")
    target_bytes, readiness_bytes = args.target.read_bytes(), args.readiness.read_bytes()
    target, readiness = json.loads(target_bytes), json.loads(readiness_bytes)
    validate_english_catalog_target(target, args.csv.read_bytes())
    report = resolve_english_catalog_target(
        target, readiness, target_bytes=target_bytes, readiness_bytes=readiness_bytes,
    )
    if args.validate:
        current = json.loads(args.output.read_text(encoding="utf-8"))
        if current != report:
            raise ValueError("Identity audit differs from its exact target/readiness inputs")
        print(json.dumps({"valid": True, "target_count": report["target_count"],
                          "identity_candidate_status_counts": report["identity_candidate_status_counts"]}, indent=2))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"target_count": report["target_count"],
                      "identity_candidate_status_counts": report["identity_candidate_status_counts"],
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
