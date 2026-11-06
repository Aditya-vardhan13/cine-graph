"""Render a hash-bound local coverage report for the supplied 1,000-title list."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.english_catalog_target_coverage import (
    build_english_catalog_target_coverage,
    render_english_catalog_target_coverage,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("data/evaluation/catalog-target-english1000-candidates-v1.json"))
    parser.add_argument("--identity-audit", type=Path, default=Path("data/evaluation/catalog-target-english1000-identity-audit-v1.json"))
    parser.add_argument("--imdb-review", type=Path, default=Path("data/evaluation/catalog-target-english1000-imdb-review-v1.json"))
    parser.add_argument("--readiness", type=Path, default=Path("data/evaluation/catalog-readiness-v7.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/catalog-target-english1000-coverage-v3.json"))
    parser.add_argument("--markdown", type=Path, default=Path("data/evaluation/catalog-target-english1000-coverage-v3.md"))
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    evaluation = (Path.cwd() / "data/evaluation").resolve()
    paths = (args.target, args.identity_audit, args.imdb_review, args.readiness, args.output, args.markdown)
    if any(not path.resolve().is_relative_to(evaluation) for path in paths):
        raise ValueError("All target audits and reports must stay under local data/evaluation")
    raw = [path.read_bytes() for path in paths[:4]]
    target, identity, imdb_review, readiness = [json.loads(data) for data in raw]
    sha = [hashlib.sha256(data).hexdigest() for data in raw]
    if identity.get("target_sha256") != sha[0] or identity.get("readiness_sha256") != sha[3]:
        raise ValueError("Identity audit fingerprints do not match the target/readiness artifacts")
    if imdb_review.get("target_sha256") != sha[0] or imdb_review.get("identity_audit_sha256") != sha[1] or imdb_review.get("readiness_sha256") != sha[3]:
        raise ValueError("IMDb review fingerprints do not match exact local inputs")
    report = build_english_catalog_target_coverage(target, identity, imdb_review, readiness)
    report["input_sha256"] = {
        "target": sha[0], "identity_audit": sha[1], "imdb_review": sha[2], "readiness": sha[3],
    }
    rendered = render_english_catalog_target_coverage(report)
    if args.validate:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        markdown = args.markdown.read_text(encoding="utf-8")
        if existing != report or markdown != rendered:
            raise ValueError("Coverage report differs from exact local inputs")
        print(json.dumps({"valid": True, "target_count": report["target_count"],
                          "catalog_candidate_mappings": report["catalog_candidate_mappings"],
                          "output": str(args.output)}, indent=2))
        return
    if args.output.exists() or args.markdown.exists():
        raise FileExistsError("Refusing to overwrite existing local coverage artifact")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with args.markdown.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
    print(json.dumps({"target_count": report["target_count"],
                      "catalog_candidate_mappings": report["catalog_candidate_mappings"],
                      "mapping_status_counts": report["mapping_status_counts"],
                      "output_json": str(args.output), "output_markdown": str(args.markdown)}, indent=2))


if __name__ == "__main__":
    main()
