"""Bind CSV director/cast to local IMDb candidate credits for human review.

This creates local review leads only. It never approves an identity, imports
IMDb text, or changes the catalog. Ambiguity and year conflicts stay visible.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from app.services.corpus_build_manifest import canonical_digest
from app.services.imdb_dataset import ImdbDataset, normalize_title


def credit_review(rows, proposal, dataset):
    output = []
    for item in proposal["rows"]:
        rank = item["target_rank"]
        raw = rows[rank - 1]
        if raw["Series_Title"].strip() != item["title"] or raw["Released_Year"].strip() != str(item["year_candidate"]):
            raise ValueError("csv_identity_or_order_changed")
        expected_director = raw["Director"].strip()
        expected_cast = [raw[f"Star{i}"].strip() for i in range(1, 5) if raw[f"Star{i}"].strip()]
        candidates = []
        for candidate in item["candidates"]:
            title_id = candidate["tconst"]
            basics = dataset.rows("basics", title_id)
            crew = dataset.rows("crew", title_id)
            principals = dataset.rows("principals", title_id)
            director_ids = {value for entry in crew for value in entry["directors"].split(",") if value != "\\N"}
            cast_ids = {entry["nconst"] for entry in principals if entry["category"] in {"actor", "actress"}}
            names = {}
            for person_id in sorted(director_ids | cast_ids):
                person = dataset.rows("names", person_id)
                if len(person) == 1:
                    names[person_id] = person[0]["primaryName"]
            directors = [{"id": value, "name": names.get(value)} for value in sorted(director_ids)]
            cast = [{"id": value, "name": names.get(value)} for value in sorted(cast_ids)]
            director_matches = [p for p in directors if p["name"] and normalize_title(p["name"]) == normalize_title(expected_director)]
            cast_matches = [{"csv_name": name, "matches": [p for p in cast if p["name"] and normalize_title(p["name"]) == normalize_title(name)]}
                            for name in expected_cast]
            candidates.append({"tconst": title_id, "title": candidate["title"], "year_delta": candidate["year_delta"],
                "basics_records": len(basics), "title_type": basics[0]["titleType"] if len(basics) == 1 else None,
                "directors": directors, "director_matches": director_matches, "cast_matches": cast_matches,
                "retained_cross_ids": candidate["retained_cross_ids"]})
        output.append({"target_rank": rank, "title": item["title"], "year_candidate": item["year_candidate"],
            "csv_director": expected_director, "csv_cast": expected_cast, "candidates": candidates,
            "identity_approved": False, "review_required": True})
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--reconciliation", type=Path, required=True)
    p.add_argument("--data-dir", type=Path, default=Path("imdb_data"))
    p.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "data" / "reports") or args.output.exists():
        raise ValueError("output_must_be_new_local_report")
    raw = args.csv.read_bytes()
    proposal = json.loads(args.proposal.read_text())
    reconciliation = json.loads(args.reconciliation.read_text())
    for obj in (proposal, reconciliation):
        if canonical_digest({k:v for k,v in obj.items() if k != "report_sha256"}) != obj["report_sha256"]:
            raise ValueError("input_report_digest_mismatch")
    if (proposal["reconciliation_sha256"] != reconciliation["report_sha256"]
            or hashlib.sha256(raw).hexdigest() != reconciliation["input_sha256"]["csv"]):
        raise ValueError("csv_or_reconciliation_binding_mismatch")
    dataset = ImdbDataset(args.data_dir, args.index_dir)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    reviewed = credit_review(rows, proposal, dataset)
    result = {"schema":"cinegraph.recovery-identity-credit-review/v1", "proposal_sha256": proposal["report_sha256"],
        "csv_sha256": hashlib.sha256(raw).hexdigest(),
        "imdb_index_source_sha256": {kind:dataset._index(kind)["sha256"] for kind in ("basics", "crew", "principals", "names")},
        "caution":"Exact normalized names are review leads, not identity approval; missing principals and aliases are not negative proof.",
        "rows":reviewed}
    result["report_sha256"] = canonical_digest(result)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"rows":len(reviewed), "with_director_match":sum(any(c["director_matches"] for c in r["candidates"]) for r in reviewed),
        "with_cast_match":sum(any(any(m["matches"] for m in c["cast_matches"]) for c in r["candidates"]) for r in reviewed),
        "report_sha256":result["report_sha256"]}))


if __name__ == "__main__":
    main()
