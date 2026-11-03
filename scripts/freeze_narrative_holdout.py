"""Freeze disjoint external case IDs without opening their gold labels."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    local = (root / "data/evaluation").resolve()
    if not local.is_relative_to(root.resolve()) or any(not p.resolve().is_relative_to(local) for p in (args.prepared, args.output)):
        raise ValueError("Input and output must remain inside project evaluation storage.")
    if args.output.exists():
        raise FileExistsError("A frozen holdout cannot be overwritten.")
    report_bytes = (args.prepared / "report.json").read_bytes()
    report = json.loads(report_bytes)
    raw = (args.prepared / "evaluation-prompts.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest() != report["outputs"]["evaluation-prompts"]["sha256"]:
        raise ValueError("Prepared input fingerprint mismatch.")
    questions = (json.loads(line) for line in raw.splitlines() if b'"case_id": "semeval:test:' in line)
    cases = [q for q in questions if q.get("source_identity_disjoint_from_dev_and_sample") is True]
    if len(cases) != report["source_identity_disjoint_test_triples"]:
        raise ValueError("Disjoint subset size differs from preparation report.")
    ids = [q["case_id"] for q in cases]
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError("Holdout IDs must be nonempty and unique.")
    manifest = {"version": "semeval-source-identity-disjoint-v1", "case_ids": ids,
        "prepared_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "prepared_prompts_sha256": hashlib.sha256(raw).hexdigest(),
        "gold_opened": False,
        "planned_models": ["qwen3-embedding:0.6b-Q8_0", "BAAI/bge-m3-dense-float32"],
        "metric": "whole-story symmetric cosine triplet accuracy; report ties",
        "caution": "Source identities are unreviewed and pretrained model exposure is unknown; not writer-usefulness or film-pair accuracy."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps({"frozen_cases": len(ids), "gold_opened": False}))


if __name__ == "__main__":
    main()
