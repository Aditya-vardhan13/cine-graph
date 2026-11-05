"""Build a model-blind local passage-review packet from a frozen capture.

Only top displayed candidates are included. Reviewers assign 0/1 labels to
the immutable chunk IDs in this packet before any accuracy claim is made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.pair_relevance_eval import score, validate_reranking


def review_items(capture: dict, rankings: list[dict]) -> list[dict]:
    cases = capture["cases"]
    if len(cases) != 50:
        raise ValueError("A review packet requires the complete 50-case capture.")
    ranked = []
    for ranking in rankings:
        ranked.append(validate_reranking(capture, ranking))
    items = []
    for case in cases:
        for side, qid, title in zip(
            ("first", "second"), case["film_qids"], case["titles"], strict=True,
        ):
            selected = [case[f"{side}_options"][0]] if case[f"{side}_options"] else []
            selected += [rows[case["case_id"]][f"{side}_ranking"][0] for rows in ranked
                         if rows[case["case_id"]][f"{side}_ranking"]]
            pool = {item["chunk_id"]: item for item in case[f"{side}_pool"]}
            for chunk_id in sorted({item["chunk_id"] for item in selected}):
                passage = pool[chunk_id]
                items.append({
                    "key": f"{case['case_id']}|{qid}|{chunk_id}",
                    "case_id": case["case_id"], "film": title, "question": case["question"],
                    "section": passage["section_title"], "passage": passage["content"],
                })
    return items


def packet_fingerprint(items: list[dict]) -> str:
    keys = "\n".join(item["key"] for item in items)
    return hashlib.sha256(keys.encode("utf-8")).hexdigest()


def labels_from_pair_sequences(items: list[dict], payload: dict) -> dict[str, int]:
    """Turn compact, hand-reviewed per-pair 0/1 strings into chunk-ID labels."""
    if payload.get("fingerprint") != packet_fingerprint(items):
        raise ValueError("Label file does not match this exact review packet.")
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item["case_id"].split("-Q")[0], []).append(item)
    sequences = payload.get("pairs", {})
    if set(sequences) != set(grouped):
        raise ValueError("Every reviewed film pair needs one label sequence.")
    labels = {}
    for pair_id, pair_items in grouped.items():
        sequence = sequences[pair_id]
        if len(sequence) != len(pair_items) or set(sequence) - {"0", "1"}:
            raise ValueError(f"Invalid or incomplete 0/1 labels for {pair_id}.")
        labels.update({item["key"]: int(value) for item, value in zip(pair_items, sequence, strict=True)})
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--ranking", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    rankings = [json.loads(path.read_text(encoding="utf-8")) for path in args.ranking]
    items = review_items(capture, rankings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = packet_fingerprint(items)
    args.output.write_text(json.dumps({"fingerprint": fingerprint, "items": items}, indent=2), encoding="utf-8")
    result = {"review_items": len(items), "fingerprint": fingerprint, "output": str(args.output)}
    if args.labels:
        labels = labels_from_pair_sequences(items, json.loads(args.labels.read_text(encoding="utf-8")))
        result["hybrid"] = score(capture, labels)
        result["rerankings"] = [score(capture, labels, reranking=ranking) for ranking in rankings]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
