"""Use the local non-commercial IMDb index to prepare review leads for misses."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.english_catalog_target import validate_english_catalog_target
from app.services.english_catalog_imdb_review import build_imdb_identity_review
from app.services.imdb_dataset import ImdbDataset


def build_report(
    target: dict, identity: dict, readiness: dict, index_path: Path, *,
    target_bytes: bytes, identity_bytes: bytes, readiness_bytes: bytes,
) -> dict:
    dataset = ImdbDataset(Path("imdb_data"), Path("data/imdb_index"))
    results = {}
    for row in identity["candidates"]:
        if row["identity_candidate_status"] not in {
            "unmatched_exact_title_year", "ambiguous_exact_title_year", "ambiguous_exact_alias_year",
        }:
            continue
        results[row["selection_rank"]] = dataset.search_title(
            row["input_title"], row["input_year"], limit=8,
        )
    report = build_imdb_identity_review(identity, readiness, results)
    report["target_sha256"] = hashlib.sha256(target_bytes).hexdigest()
    report["identity_audit_sha256"] = hashlib.sha256(identity_bytes).hexdigest()
    report["readiness_sha256"] = hashlib.sha256(readiness_bytes).hexdigest()
    report["imdb_title_index_sha256"] = hashlib.sha256(index_path.read_bytes()).hexdigest()
    report["index_lookup_policy"] = "Local exact/fuzzy title lookup constrained to input year +/- 1; max 8 results per unresolved row"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("imdb_top_1000.csv"))
    parser.add_argument("--target", type=Path, default=Path("data/evaluation/catalog-target-english1000-candidates-v1.json"))
    parser.add_argument("--identity-audit", type=Path, default=Path("data/evaluation/catalog-target-english1000-identity-audit-v1.json"))
    parser.add_argument("--readiness", type=Path, default=Path("data/evaluation/catalog-readiness-v7.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("imdb_data"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/catalog-target-english1000-imdb-review-v1.json"))
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    if args.csv.resolve() != (project / "imdb_top_1000.csv").resolve():
        raise ValueError("Candidate CSV must be the supplied project imdb_top_1000.csv")
    if args.data_dir.resolve() != (project / "imdb_data").resolve() or args.index_dir.resolve() != (project / "data/imdb_index").resolve():
        raise ValueError("IMDb inputs must be the existing local project datasets/index")
    local_paths = (args.target, args.identity_audit, args.readiness, args.output)
    if any(not path.resolve().is_relative_to(evaluation) for path in local_paths):
        raise ValueError("Target, audits and output must stay under local data/evaluation")
    target_bytes, identity_bytes, readiness_bytes = (
        args.target.read_bytes(), args.identity_audit.read_bytes(), args.readiness.read_bytes(),
    )
    target, identity, readiness = [json.loads(data) for data in (target_bytes, identity_bytes, readiness_bytes)]
    validate_english_catalog_target(target, args.csv.read_bytes())
    if identity.get("target_sha256") != hashlib.sha256(target_bytes).hexdigest():
        raise ValueError("Identity audit is not bound to the exact candidate manifest bytes")
    if identity.get("readiness_sha256") != hashlib.sha256(readiness_bytes).hexdigest():
        raise ValueError("Identity audit is not bound to the exact readiness report bytes")
    index_path = args.index_dir / "titles.sqlite"
    if not index_path.is_file():
        raise FileNotFoundError(index_path)
    report = build_report(target, identity, readiness, index_path,
                          target_bytes=target_bytes, identity_bytes=identity_bytes,
                          readiness_bytes=readiness_bytes)
    if args.validate:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != report:
            raise ValueError("IMDb review differs from its exact local inputs/index")
        print(json.dumps({"valid": True, "review_queue_count": report["review_queue_count"],
                          "candidate_status_counts": report["candidate_status_counts"]}, indent=2))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"review_queue_count": report["review_queue_count"],
                      "candidate_status_counts": report["candidate_status_counts"],
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
