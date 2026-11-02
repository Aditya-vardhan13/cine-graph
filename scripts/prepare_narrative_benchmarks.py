"""Offline, versioned research-data preparation. Never connects to a database/model."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.external_narrative_preparation import (
    category_set, claim_arms, claim_pair_status, narrative_case, passage_windows, srt_text, text_id,
)
from app.services.lexical_retrieval import Bm25Index

VERSION = "external-narrative-preparation-v1"
REVISIONS = {"narrative-similarity": "ef7375dd08172c804ffa6706aa94d003e59f5015",
             "mf2": "e00ff56479c88fcc9947d4975c8deba93e42e922"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    allowed = (ROOT / "data/evaluation").resolve()
    if not allowed.is_relative_to(ROOT.resolve()) or not args.output.resolve().is_relative_to(allowed):
        raise ValueError("Outputs must stay in this project's local evaluation storage.")
    # Each invocation creates a distinct run. Never overwrite a successful run.
    args.output.mkdir(parents=True, exist_ok=False)
    roots, captures, inputs = {}, {}, []
    for dataset, revision in REVISIONS.items():
        base = ROOT / "data/evaluation/external" / dataset / revision
        manifest = json.loads((base / "acquisition-manifest.json").read_text())
        if manifest["revision"] != revision:
            raise ValueError("Acquired revision mismatch.")
        for item in manifest["files"]:
            path = base / item["path"]
            if not path.resolve().is_relative_to(allowed):
                raise ValueError("Input source escapes local evaluation storage.")
            payload = path.read_bytes()
            if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
                raise ValueError(f"Snapshot integrity failure: {path}")
            captures[(dataset, item["path"])] = item
        roots[dataset] = base
        inputs.append({"dataset": dataset, "revision": revision,
                       "manifest_sha256": text_id((base / "acquisition-manifest.json").read_text())})
    docs, prompts, gold, quarantine, errors = {}, [], [], [], []
    def add_doc(dataset, filename, content, identity, locator, kind, maps=None):
        if not content.strip():
            raise ValueError("Empty evidence document.")
        identifier = (text_id(content) if dataset == "narrative-similarity" else
                      f"mf2:{identity['dataset_movie_id']}:{kind}")
        record = captures[(dataset, filename)]
        source = {"url": record["url"], "snapshot_sha256": record["sha256"],
                  "relative_path": filename, "locator": locator}
        if identifier not in docs:
            docs[identifier] = {"document_id": identifier, "dataset": dataset, "kind": kind,
                "content": content, "content_sha256": text_id(content), "source_occurrences": [],
                "identities": [], "licence": "CC BY-SA 4.0" if dataset == "narrative-similarity" else "CC BY 4.0 (release declaration)",
                "use_scope": "local-research-evaluation-only", "operational_eligible": False,
                "canonical_identity_status": "unreviewed", "cue_source_map": maps or []}
        docs[identifier]["source_occurrences"].append(source)
        if identity not in docs[identifier]["identities"]:
            docs[identifier]["identities"].append(identity)
        return identifier
    split_texts = {}
    for split in ("dev", "sample", "test"):
        filename = f"{split}/{split}_track_a.jsonl"
        labels = []
        if split == "test":
            labels = [json.loads(line) for line in (roots["narrative-similarity"] / "test/labels/test_track_a_labels.jsonl").read_text().splitlines()]
        rows = [json.loads(line) for line in (roots["narrative-similarity"] / filename).read_text().splitlines()]
        if labels and len(labels) != len(rows):
            raise ValueError("Test labels and questions have unequal lengths.")
        split_texts[split] = set()
        for i, row in enumerate(rows):
            case_id = f"semeval:{split}:{i}"
            prompt, expected = narrative_case(row, split=split, case_id=case_id)
            if labels:
                label = labels[i]
                # Validate exact source texts before using positional label alignment.
                for key in ("anchor_text", "text_a", "text_b"):
                    if label.get(key) != row[key]:
                        raise ValueError("Test label text does not align exactly with question.")
                _, expected = narrative_case(label, split=split, case_id=case_id)
            for role, key, metadata in (("anchor", "anchor_text", "story_details_anchor"),
                                        ("a", "text_a", "story_details_a"), ("b", "text_b", "story_details_b")):
                identity = row.get(metadata) or (labels[i].get(metadata, {}) if labels else {})
                identity = {**identity, "metadata_source_path": "test/labels/test_track_a_labels.jsonl" if labels else filename,
                            "metadata_source_line": i + 1, "metadata_source_field": metadata}
                doc_id = add_doc("narrative-similarity", filename, row[key], identity,
                                 {"jsonl_line": i + 1, "field": key}, "story_summary")
                split_texts[split].add(doc_id)
            prompt["exact_text_disjoint_from_dev_and_sample"] = (
                split == "test" and not set(prompt["stories"].values()) &
                (split_texts["dev"] | split_texts["sample"]))
            prompts.append(prompt)
            if expected:
                gold.append(expected)
    seen_work_ids = {identity.get("wikidata_id") for q in prompts if q["official_split"] in {"dev", "sample"}
                     for doc_id in q["stories"].values() for identity in docs[doc_id]["identities"]
                     if identity.get("wikidata_id")}
    for q in prompts:
        work_ids = [{identity.get("wikidata_id") for identity in docs[doc_id]["identities"]
                     if identity.get("wikidata_id")} for doc_id in q["stories"].values()]
        q["source_identity_disjoint_from_dev_and_sample"] = (q["official_split"] == "test"
            and q["exact_text_disjoint_from_dev_and_sample"] and all(work_ids)
            and not set.union(*work_ids) & seen_work_ids)
    mf_file = "data/MF2_test.csv"
    mf_rows = list(csv.DictReader((roots["mf2"] / mf_file).open()))
    if len({(r["movie_id"], r["claim_id"]) for r in mf_rows}) != len(mf_rows):
        raise ValueError("Duplicate MF2 film/claim identities.")
    for identity in sorted({r["movie_id"] for r in mf_rows}, key=int):
        for kind, filename in (("transcript", f"data/transcripts/{identity}.srt"),
                               ("synopsis", f"data/synopsis/{identity}.synopsis")):
            try:
                # Decode bytes without newline normalization; source offsets stay exact.
                raw = (roots["mf2"] / filename).read_bytes().decode("utf-8")
                content, maps = srt_text(raw) if kind == "transcript" else (raw, [])
                for cue in maps:
                    assert raw[cue["raw_start"]:cue["raw_end"]] == content[cue["content_start"]:cue["content_end"]]
                add_doc("mf2", filename, content, {"dataset_movie_id": identity},
                        {"kind": "srt-cues" if maps else "full-text"}, kind, maps)
            except (ValueError, UnicodeError) as exc:
                errors.append({"source": filename, "reason": str(exc)})
    mf_capture = captures[("mf2", mf_file)]
    for i, row in enumerate(mf_rows):
        case_id = f"mf2:{row['movie_id']}:{row['claim_id']}"
        status = claim_pair_status(row)
        if status != "eligible_for_review":
            quarantine.append({"case_id": case_id, "reason": status, "csv_row": i + 2})
            continue
        source_docs = [key for key in (f"mf2:{row['movie_id']}:transcript",
                                      f"mf2:{row['movie_id']}:synopsis") if key in docs]
        # Identities are dataset-local, not invented Wikidata/IMDb film identities.
        for arm, claim, value in claim_arms(case_id, row):
            question_id = f"{case_id}:{arm}"
            prompts.append({"case_id": question_id, "dataset": "mf2", "official_split": "test",
                "task": "claim_verification", "claim": claim, "pair_id": case_id,
                "evidence_document_ids": source_docs, "evidence_sufficiency": "unreviewed-may-require-video"})
            gold.append({"case_id": question_id, "expected_truth": value,
                "categories": category_set(row["category"]), "raw_category": row["category"],
                "granularity": row["granularity"], "source_url": mf_capture["url"],
                "source_snapshot_sha256": mf_capture["sha256"], "csv_row": i + 2})
    passages = []
    for doc in docs.values():
        for index, span in enumerate(passage_windows(doc["content"])):
            passages.append({"passage_id": f"{doc['document_id']}:{index}",
                "document_id": doc["document_id"], "dataset": doc["dataset"], **span})
    outputs = {}
    for name, rows in (("evidence-documents", list(docs.values())), ("evidence-passages", passages),
                       ("evaluation-prompts", prompts), ("gold-labels", gold),
                       ("quarantine", quarantine), ("source-errors", errors)):
        payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
        (args.output / f"{name}.jsonl").write_text(payload)
        outputs[name] = {"rows": len(rows), "sha256": text_id(payload)}
    # Cheap development-only control. Gold is used for scoring, not retrieval inputs.
    lookup = {row["case_id"]: row for row in gold}
    decisions = []
    started = perf_counter()
    for question in prompts:
        if question["dataset"] != "narrative-similarity" or question["official_split"] != "dev":
            continue
        story = question["stories"]
        scores = Bm25Index.build([docs[story[key]]["content"] for key in ("a", "b")]).scores(docs[story["anchor"]]["content"])
        decisions.append(None if scores[0] == scores[1] else (scores[0] > scores[1]) == lookup[question["case_id"]]["a_is_closer"])
    report = {"version": VERSION, "inputs": inputs, "outputs": outputs,
        "source_errors": errors, "status": "needs-source-review" if errors else "prepared-not-product-published",
        "split_overlap_exact_texts": {f"{a}/{b}": len(split_texts[a] & split_texts[b])
             for a, b in (("dev", "sample"), ("dev", "test"), ("sample", "test"))},
        "exact_text_disjoint_test_triples": sum(q.get("exact_text_disjoint_from_dev_and_sample", False) for q in prompts),
        "source_identity_disjoint_test_triples": sum(q.get("source_identity_disjoint_from_dev_and_sample", False) for q in prompts),
        "lexical_control": {"task": "SemEval Track A dev only", "cases": len(decisions),
             "correct": decisions.count(True), "incorrect": decisions.count(False), "ties": decisions.count(None),
             "accuracy_including_ties_as_failures": decisions.count(True) / len(decisions),
             "seconds": perf_counter() - started,
             "caution": "Lexical two-candidate BM25 diagnostic, not film RAG accuracy or writer usefulness."},
        "caution": "Research-only derivatives; no labels in evidence; upstream identity and rights review required."}
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    if errors:
        sys.exit(2)


if __name__ == "__main__":
    main()
