"""Offline source-diversity ablation on an existing unscored diagnostic pool."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.narrative_retrieval_packet import interleave_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranking_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    local = (ROOT / "data/evaluation").resolve()
    if not local.is_relative_to(ROOT.resolve()) or any(not p.resolve().is_relative_to(local) for p in (args.ranking_dir, args.output)):
        raise ValueError("Inputs and outputs must remain in project evaluation storage.")
    source = args.ranking_dir / "rankings.jsonl"
    contract = json.loads((args.ranking_dir / "contract.json").read_text())
    raw = source.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    if [row["case_id"] for row in rows] != contract["case_ids"]:
        raise ValueError("Ranking case IDs disagree with the frozen contract.")
    args.output.mkdir(parents=True, exist_ok=False)
    changes = Counter()
    with (args.output / "rankings.jsonl").open("x") as output:
        for row in rows:
            original = row["ranked"]
            diversified = interleave_sources(original, limit=contract["top_k"])
            for k in (2, 3, 6):
                before = len({p["document_id"] for p in original[:k]})
                after = len({p["document_id"] for p in diversified[:k]})
                changes[f"both_sources_before_at_{k}"] += before == 2
                changes[f"both_sources_after_at_{k}"] += after == 2
            output.write(json.dumps({**row, "ranked": diversified}, sort_keys=True) + "\n")
    result = {"version": "mf2-pool-interleave-v1", "source_rankings_sha256": hashlib.sha256(raw).hexdigest(),
              "cases": len(rows), "source_visibility": dict(changes), "gold_file_opened": False,
              "caution": "Source diversity only. No evidence relevance, entailment, or accuracy was assessed."}
    (args.output / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
