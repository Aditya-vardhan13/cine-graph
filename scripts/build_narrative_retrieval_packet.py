"""Offline MF2 diagnostic-dev retrieval worker. No gold file or model access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.narrative_retrieval_packet import diagnostic_dev_film, rank_claim


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    local = (ROOT / "data/evaluation").resolve()
    if not local.is_relative_to(ROOT.resolve()) or any(not p.resolve().is_relative_to(local) for p in (args.run, args.output)):
        raise ValueError("Worker inputs and outputs must stay in project evaluation storage.")
    args.output.mkdir(parents=True, exist_ok=False)
    report = json.loads((args.run / "report.json").read_text())
    data = {}
    for name in ("evidence-passages", "evaluation-prompts"):
        payload = (args.run / f"{name}.jsonl").read_bytes()
        if hashlib.sha256(payload).hexdigest() != report["outputs"][name]["sha256"]:
            raise ValueError("Prepared input fingerprint mismatch.")
        data[name] = [json.loads(line) for line in payload.decode().splitlines()]
    questions = [q for q in data["evaluation-prompts"] if q["dataset"] == "mf2"]
    selected = [q for q in questions if diagnostic_dev_film(q["evidence_document_ids"][0])]
    selected_ids = [q["case_id"] for q in selected]
    contract = {"version": "mf2-lexical-diagnostic-dev-v1", "top_k": 6,
                "selection": "sha256 of mf2-diagnostic-split-v1:<film-id> modulo 5 equals zero",
                "source_report_sha256": hashlib.sha256((args.run / "report.json").read_bytes()).hexdigest(),
                "passages_sha256": report["outputs"]["evidence-passages"]["sha256"],
                "prompts_sha256": report["outputs"]["evaluation-prompts"]["sha256"],
                "case_ids": selected_ids,
                "caution": "Derived diagnostic-development subset of official test; never claim it as untouched test."}
    (args.output / "contract.json").write_text(json.dumps(contract, indent=2))
    started = perf_counter()
    with (args.output / "rankings.jsonl").open("x") as stream:
        for index, question in enumerate(selected, 1):
            packet = rank_claim(question, data["evidence-passages"], top_k=contract["top_k"])
            stream.write(json.dumps(packet, sort_keys=True) + "\n")
            stream.flush()
            if index % 25 == 0:
                print(f"retrieved {index}/{len(selected)}", flush=True)
    summary = {"status": "completed-unscored-leads", "questions": len(selected),
               "diagnostic_film_count": len({q["evidence_document_ids"][0] for q in selected}),
               "untouched_claim_questions": len(questions) - len(selected),
               "seconds": perf_counter() - started,
               "gold_file_opened": False, "model_loaded": False,
               "note": "No accuracy or semantic-support claim. Separate development source review required."}
    (args.output / "report.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
