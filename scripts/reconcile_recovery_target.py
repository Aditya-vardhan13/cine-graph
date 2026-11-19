"""Bind frozen CSV target candidates to current source-build readiness, without approval."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
from app.services.corpus_build_manifest import canonical_digest


def reconcile(csv_bytes, target_bytes, coverage_bytes, build_bytes):
    target, coverage, build = map(json.loads, (target_bytes, coverage_bytes, build_bytes))
    if hashlib.sha256(csv_bytes).hexdigest() != target["input_sha256"]:
        raise ValueError("csv_target_fingerprint_mismatch")
    if coverage["input_sha256"]["target"] != hashlib.sha256(target_bytes).hexdigest():
        raise ValueError("coverage_target_fingerprint_mismatch")
    payload = {k: v for k, v in build.items() if k != "manifest_sha256"}
    if canonical_digest(payload) != build["manifest_sha256"]:
        raise ValueError("build_manifest_fingerprint_mismatch")
    targets = target["candidates"]
    if [t["selection_rank"] for t in targets] != list(range(1, len(targets)+1)):
        raise ValueError("target_ranks_not_contiguous")
    csv_rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    if len(csv_rows) < len(targets):
        raise ValueError("csv_shorter_than_target")
    previous = {}
    for row in coverage["films"]:
        if row["selection_rank"] in previous:
            raise ValueError("duplicate_coverage_rank")
        previous[row["selection_rank"]] = row
    if set(previous) != set(range(1, len(targets)+1)):
        raise ValueError("coverage_rank_set_mismatch")
    current = defaultdict(list)
    for film in build["films"]:
        if film.get("wikidata_id"):
            current[film["wikidata_id"]].append(film)
    rows = []
    for t, raw in zip(targets, csv_rows):
        if raw["Series_Title"].strip() != t["title"] or raw["Released_Year"].strip() != str(t["release_year_candidate"]):
            raise ValueError("csv_title_order_mismatch")
        historical = previous[t["selection_rank"]]
        candidates = current.get(historical.get("wikidata_id"), [])
        status = ("current_candidate" if len(candidates) == 1 else
                  "ambiguous_current_qid" if candidates else "unresolved_or_outside_collection")
        rows.append({"target_rank": t["selection_rank"], "title": t["title"],
            "year_candidate": t["release_year_candidate"], "identity_review": "required",
            "status": status, "historical_mapping_status": historical["mapping_status"],
            "historical_candidate_qid": historical.get("wikidata_id"),
            "current_candidates": [{"entity_id": f["entity_id"], "title": f["title"],
                "build_eligible": f["build_eligible"],
                "source_snapshot_ids": [s["snapshot_id"] for s in f["sources"]]} for f in candidates]})
    result = {"schema": "cinegraph.recovery-target-reconciliation/v1",
        "target_rows": len(targets), "csv_rows": len(csv_rows),
        "csv_rows_outside_frozen_target": len(csv_rows)-len(targets),
        "statuses": dict(Counter(r["status"] for r in rows)),
        "identity_approved": 0, "target_rows_with_eligible_candidate": sum(
            any(f["build_eligible"] for f in r["current_candidates"]) for r in rows),
        "input_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in
            zip(("csv", "target", "historical_coverage", "current_build"), (csv_bytes,target_bytes,coverage_bytes,build_bytes))},
        "rows": rows}
    return {**result, "report_sha256": canonical_digest(result)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("csv", "target", "coverage", "build", "output"):
        p.add_argument("--"+flag, type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = reconcile(*(getattr(args, k).read_bytes() for k in ("csv","target","coverage","build")))
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k != "rows"}))


if __name__ == "__main__":
    main()
