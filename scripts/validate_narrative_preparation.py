"""Read-only retained-source/derivative audit. Does not read labels into model inputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    local = root / "data/evaluation"
    if not local.resolve().is_relative_to(root.resolve()) or not args.run.resolve().is_relative_to(local.resolve()):
        raise ValueError("Only project-local evaluation runs can be audited.")
    report = json.loads((args.run / "report.json").read_text())
    files = {}
    for name, expected in report["outputs"].items():
        path = args.run / f"{name}.jsonl"
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected["sha256"]:
            raise ValueError(f"Changed derivative: {name}")
        files[name] = [json.loads(line) for line in payload.decode().splitlines()]
        require(len(files[name]) == expected["rows"], f"Row-count mismatch: {name}")
    docs = {r["document_id"]: r for r in files["evidence-documents"]}
    require(len(docs) == len(files["evidence-documents"]), "Duplicate document IDs.")
    captures = {}
    for source in report["inputs"]:
        base = root / "data/evaluation/external" / source["dataset"] / source["revision"]
        require(base.resolve().is_relative_to(local.resolve()), "Source directory escapes project storage.")
        manifest_raw = (base / "acquisition-manifest.json").read_bytes()
        require(hashlib.sha256(manifest_raw).hexdigest() == source["manifest_sha256"], "Source manifest changed.")
        for path in base.rglob("*"):
            if path.is_file() and path.name != "acquisition-manifest.json":
                require(path.resolve().is_relative_to(local.resolve()), "Source file escapes project storage.")
                captures[(source["dataset"], str(path.relative_to(base)))] = path.read_bytes()
    cue_count, untimed = 0, 0
    for doc in docs.values():
        require(doc["operational_eligible"] is False, "Research data promoted to operational evidence.")
        require(doc["use_scope"] == "local-research-evaluation-only", "Unexpected usage scope.")
        require(hashlib.sha256(doc["content"].encode()).hexdigest() == doc["content_sha256"], "Changed document content.")
        require(bool(doc["source_occurrences"]), "Evidence lacks a source.")
        for occurrence in doc["source_occurrences"]:
            raw = captures[(doc["dataset"], occurrence["relative_path"])]
            require(hashlib.sha256(raw).hexdigest() == occurrence["snapshot_sha256"], "Source checksum mismatch.")
            value = raw.decode()
            locator = occurrence["locator"]
            if "jsonl_line" in locator:
                require(json.loads(value.splitlines()[locator["jsonl_line"] - 1])[locator["field"]] == doc["content"], "Summary source binding failed.")
            elif doc["kind"] == "synopsis":
                require(value == doc["content"], "Synopsis source binding failed.")
            else:
                require(bool(doc["cue_source_map"]), "Transcript lacks source maps.")
                rendered = []
                for cue in doc["cue_source_map"]:
                    require(0 <= cue["raw_start"] < cue["raw_end"] <= len(value), "Raw cue offsets invalid.")
                    require(0 <= cue["content_start"] < cue["content_end"] <= len(doc["content"]), "Rendered cue offsets invalid.")
                    require(value[cue["raw_start"]:cue["raw_end"]] == doc["content"][cue["content_start"]:cue["content_end"]], "Cue source binding failed.")
                    rendered.append(value[cue["raw_start"]:cue["raw_end"]])
                    cue_count += 1
                    untimed += cue["timestamp_status"] == "untimed-source-block"
                require("\n".join(rendered) == doc["content"], "Cue maps do not cover the rendered transcript.")
    coverage = {}
    for passage in files["evidence-passages"]:
        identifier = passage["document_id"]
        doc = docs[identifier]
        require(0 <= passage["start"] < passage["end"] <= len(doc["content"]), "Passage offsets invalid.")
        require(passage["content"] == doc["content"][passage["start"]:passage["end"]], "Passage source binding failed.")
        require(passage["start"] <= coverage.get(identifier, 0) or not doc["content"][coverage.get(identifier, 0):passage["start"]].strip(), "Passage coverage has a gap.")
        coverage[identifier] = max(coverage.get(identifier, 0), passage["end"])
    require(set(coverage) == set(docs), "Some documents have no passages.")
    require(all(not docs[k]["content"][end:].strip() for k, end in coverage.items()), "Passage coverage loses document tails.")
    prompts, gold = files["evaluation-prompts"], files["gold-labels"]
    require(len({p["case_id"] for p in prompts}) == len(prompts), "Duplicate question IDs.")
    require(len({g["case_id"] for g in gold}) == len(gold), "Duplicate gold IDs.")
    require({p["case_id"] for p in prompts} == {g["case_id"] for g in gold}, "Question/gold IDs disagree.")
    for prompt in prompts:
        require(not set(prompt) & {"expected_truth", "a_is_closer", "human_labels", "dimensions", "true_claim", "false_claim"}, "Labels leaked into model input.")
        if prompt["dataset"] == "mf2":
            require(len(prompt["evidence_document_ids"]) == 2, "Claim lacks both source documents.")
            require(all(i in docs for i in prompt["evidence_document_ids"]), "Claim evidence is missing.")
        else:
            require(all(i in docs for i in prompt["stories"].values()), "Story evidence is missing.")
    quarantined = {q["case_id"] for q in files["quarantine"]}
    require(not quarantined & {p.get("pair_id") for p in prompts}, "Quarantined pairs included in evaluation.")
    require(not files["source-errors"], "Source parsing failures require review.")
    print(json.dumps({"status": "integrity-and-source-maps-verified-not-semantic-quality",
        "documents": len(docs), "passages": len(files["evidence-passages"]), "prompts": len(prompts),
        "subtitle_source_spans_checked": cue_count, "untimed_source_blocks": untimed,
        "quarantined_pairs": len(quarantined),
        "document_kinds": dict(Counter(d["kind"] for d in docs.values())),
        "caution": "Checks source binding and label separation, not subtitle accuracy or answer entailment."}, indent=2))


if __name__ == "__main__":
    main()
