"""Build a small, reproducible source-review packet without consulting gold labels."""
import argparse
import hashlib
import json
from pathlib import Path


def select_review_cases(rows, passages):
    groups = {}
    for row in rows:
        film = row["evidence_document_ids"][0].split(":")[1]
        groups.setdefault(film, []).append(row)
    sample = []
    for film, cases in sorted(groups.items(), key=lambda item: int(item[0])):
        cases.sort(key=lambda r: hashlib.sha256(r["case_id"].encode()).hexdigest())
        for row in cases[:2]:
            leads = []
            for lead in row["ranked"]:
                passage = passages[lead["passage_id"]]
                if any(passage[k] != lead[k] for k in ("document_id", "start", "end")):
                    raise ValueError("Ranked passage provenance mismatch.")
                leads.append({**lead, "content": passage["content"]})
            sample.append({"case_id": row["case_id"], "dataset_movie_id": film,
                           "claim": row["claim"], "leads": leads,
                           "review_status": "not-reviewed"})
    return sample, len(groups)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("rankings", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    local = (root / "data/evaluation").resolve()
    if not local.is_relative_to(root.resolve()) or any(not p.resolve().is_relative_to(local) for p in (args.prepared, args.rankings, args.output)):
        raise ValueError("Inputs and output must remain inside project evaluation storage.")
    if args.output.exists():
        raise FileExistsError("Never overwrite an existing review packet.")
    report = json.loads((args.prepared / "report.json").read_text())
    raw = (args.prepared / "evidence-passages.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest() != report["outputs"]["evidence-passages"]["sha256"]:
        raise ValueError("Passage fingerprint mismatch.")
    passages = {p["passage_id"]: p for p in (json.loads(line) for line in raw.splitlines())}
    ranking_file = args.rankings / "rankings.jsonl"
    contract = json.loads((args.rankings / "contract.json").read_text())
    if contract["passages_sha256"] != report["outputs"]["evidence-passages"]["sha256"]:
        raise ValueError("Rankings and source passage fingerprints disagree.")
    rows = [json.loads(line) for line in ranking_file.read_text().splitlines()]
    if [r["case_id"] for r in rows] != contract["case_ids"]:
        raise ValueError("Rankings do not match frozen contract.")
    # Hash-based sampling does not inspect claims, answers or ranking results.
    sample, film_count = select_review_cases(rows, passages)
    output = {"version": "mf2-blind-source-review-sample-v2", "gold_file_opened": False,
              "rankings_sha256": hashlib.sha256(ranking_file.read_bytes()).hexdigest(),
              "passages_sha256": report["outputs"]["evidence-passages"]["sha256"],
              "sampling": "two cases per diagnostic film, ordered by SHA-256 of case ID",
              "cases": sample,
              "caution": "Review relevance and support manually; an exact excerpt is not an entailment."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2))
    print(json.dumps({"status": "prepared-not-reviewed", "films": film_count, "cases": len(sample)}))


if __name__ == "__main__":
    main()
