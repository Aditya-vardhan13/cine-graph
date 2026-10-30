"""Blind, content-bound top-one review across two local retrieval canaries.

Inputs and outputs stay under ignored project-local data/evaluation. The packet
does not disclose which index or section policy returned each passage; a
separate mapping is scored only after every passage receives a review label.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VARIANTS = ("v1-restricted", "v1-whole-film", "v2-restricted", "v2-whole-film")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_packet(v1: dict, v2: dict, *, depth: int = 1) -> tuple[dict, dict]:
    if depth not in (1, 3):
        raise ValueError("Only top-one and top-three review depths are supported.")
    if v1.get("case_count") != v2.get("case_count") or v1.get("case_count") != 20:
        raise ValueError("A first-stage review requires the same twenty frozen questions.")
    if v1.get("method") != v2.get("method") or v1["method"] != "hybrid":
        raise ValueError("The two trials must use the same hybrid retrieval method.")
    items = []
    mapping = []
    for first, second in zip(v1["results"], v2["results"], strict=True):
        if first["case_id"] != second["case_id"] or first["question"] != second["question"]:
            raise ValueError("The two captures do not share a frozen question.")
        for v1_side, v2_side in zip(first["sides"], second["sides"], strict=True):
            if v1_side["film_qid"] != v2_side["film_qid"]:
                raise ValueError("The two captures do not share a film identity.")
            candidates = {}
            chosen = {}
            for prefix, side in (("v1", v1_side), ("v2", v2_side)):
                for suffix, field in (("restricted", "restricted_top_three"),
                                      ("whole-film", "whole_film_top_three")):
                    variant = f"{prefix}-{suffix}"
                    options = side[field]
                    keys = []
                    for passage in options[:depth]:
                        identity = {
                            "case_id": first["case_id"],
                            "film_qid": side["film_qid"],
                            "question": first["question"],
                            "source_snapshot_id": passage["source_snapshot_id"],
                            "section": passage["section_locator"],
                            "passage": passage["content"],
                        }
                        digest = hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()
                        key = f"{first['case_id']}|{side['film_qid']}|{digest[:20]}"
                        candidates[key] = {"key": key, **identity}
                        keys.append(key)
                    chosen[variant] = (keys[0] if keys else None) if depth == 1 else keys
            items.extend(candidates.values())
            mapping.append({
                "case_id": first["case_id"], "film_qid": v1_side["film_qid"],
                "variants": chosen,
            })
    items.sort(key=lambda item: item["key"])
    fingerprint = hashlib.sha256(_canonical(items).encode("utf-8")).hexdigest()
    return (
        {"version": "pair-canary-review-v1" if depth == 1 else "pair-canary-review-depth-3-v1",
         "fingerprint": fingerprint, "items": items},
        {"fingerprint": fingerprint, "variants": VARIANTS, "depth": depth, "mapping": mapping},
    )


def score(packet: dict, mapping: dict, labels: dict) -> dict:
    fingerprint = packet["fingerprint"]
    actual_fingerprint = hashlib.sha256(_canonical(packet["items"]).encode("utf-8")).hexdigest()
    if (actual_fingerprint != fingerprint or mapping.get("fingerprint") != fingerprint
            or labels.get("fingerprint") != fingerprint):
        raise ValueError("Review labels and rankings must bind the full question and passage content.")
    by_key = labels.get("labels")
    if by_key is None and "cases" in labels:
        by_key = {}
        grouped = {}
        for item in packet["items"]:
            grouped.setdefault(item["case_id"], []).append(item)
        if set(grouped) != set(labels["cases"]):
            raise ValueError("Every frozen question needs one review sequence.")
        names = {"D": "direct", "P": "partial", "I": "irrelevant"}
        for case_id, items in grouped.items():
            review = labels["cases"][case_id]
            sequence = review.get("sequence", "")
            rationale = review.get("rationale", "").strip()
            if len(sequence) != len(items) or set(sequence) - set(names) or not rationale:
                raise ValueError(f"Incomplete review sequence or rationale for {case_id}.")
            by_key.update({
                item["key"]: {"support": names[code], "rationale": rationale}
                for item, code in zip(items, sequence, strict=True)
            })
    if by_key is None:
        by_key = {}
    expected = {item["key"] for item in packet["items"]}
    if set(by_key) != expected:
        raise ValueError("Every blinded passage needs exactly one review label.")
    valid = {"direct", "partial", "irrelevant"}
    if any(value.get("support") not in valid or not value.get("rationale", "").strip()
           for value in by_key.values()):
        raise ValueError("Each review requires direct/partial/irrelevant support and a rationale.")
    rows = []
    for row in mapping["mapping"]:
        supports = {}
        for variant, selected in row["variants"].items():
            keys = selected if isinstance(selected, list) else ([selected] if selected is not None else [])
            supports[variant] = [by_key[key]["support"] for key in keys]
        rows.append({"case_id": row["case_id"], "film_qid": row["film_qid"], "supports": supports})
    metrics = {}
    depth = mapping.get("depth", 1)
    for variant in VARIANTS:
        side_direct = sum("direct" in row["supports"][variant] for row in rows)
        cases = {}
        for row in rows:
            cases.setdefault(row["case_id"], []).append("direct" in row["supports"][variant])
        pair_direct = sum(len(sides) == 2 and all(sides) for sides in cases.values())
        metrics[variant] = {
            "direct_sides": side_direct,
            "sides": len(rows),
            "direct_pairs": pair_direct,
            "pairs": len(cases),
            f"pair_success_at_{depth}": round(pair_direct / len(cases), 4),
        }
    by_case = {}
    for row in rows:
        by_case.setdefault(row["case_id"], []).append(
            any("direct" in row["supports"][variant] for variant in VARIANTS)
        )
    head_oracle_pairs = sum(len(sides) == 2 and all(sides) for sides in by_case.values())
    return {
        "fingerprint": fingerprint, "reviewed_passages": len(expected), "metrics": metrics,
        "head_oracle": {
            "direct_pairs": head_oracle_pairs, "pairs": len(by_case),
            "caution": f"Only the four displayed top-{depth} variants, not the full candidate pool.",
        },
    }


def _local_report(path: Path) -> Path:
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Review artifacts must stay under ignored project-local data/evaluation.")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v1", type=Path)
    parser.add_argument("v2", type=Path)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--depth", type=int, choices=(1, 3), default=1)
    args = parser.parse_args()
    paths = [_local_report(path) for path in (args.v1, args.v2, args.packet, args.mapping)]
    v1, v2 = (json.loads(path.read_text(encoding="utf-8")) for path in paths[:2])
    packet, mapping = make_packet(v1, v2, depth=args.depth)
    for path, payload in zip(paths[2:], (packet, mapping), strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {"fingerprint": packet["fingerprint"], "questions": 20, "review_passages": len(packet["items"])}
    if args.labels is not None:
        result["score"] = score(packet, mapping, json.loads(_local_report(args.labels).read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
