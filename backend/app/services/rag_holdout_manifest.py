"""Resolve frozen holdout titles to explicit identities; never inspect rankings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def build_manifest(questions: dict, identities: dict, *, collection: str) -> dict:
    if not collection.strip():
        raise ValueError("An explicit source collection is required.")
    mapping = {}
    for film in identities["films"]:
        key = (film["title"], film["year"])
        qid = film["qid"]
        if key in mapping or not re.fullmatch(r"Q[1-9][0-9]*", qid):
            raise ValueError("Identity mapping must have unique title-years and valid QIDs.")
        mapping[key] = qid
    pairs, used = [], []
    for pair in questions["pairs"]:
        titles = [(film["title"], film["year"]) for film in pair["films"]]
        if len(titles) != 2 or any(key not in mapping for key in titles):
            raise ValueError("Each selected film needs an explicit frozen identity.")
        used.extend(titles)
        pairs.append({"id": pair["id"], "films": [mapping[key] for key in titles],
                      "titles": [title for title, _ in titles], "questions": pair["questions"]})
    if len(set(used)) != len(used) or set(used) != set(mapping) or len(set(mapping.values())) != len(mapping):
        raise ValueError("Holdout films and QIDs must be one-to-one and exactly matched.")
    return {"version": f"{questions['version']}+{identities['version']}", "collection": collection,
            "status": "unlabelled-not-a-validated-holdout", "pairs": pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("identities", type=Path)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if any(not path.resolve().is_relative_to(root) for path in (args.questions, args.identities)):
        raise ValueError("Use project-local frozen design inputs.")
    if not args.output.resolve().is_relative_to(root / "data" / "evaluation"):
        raise ValueError("Output must remain in project-local evaluation storage.")
    manifest = build_manifest(json.loads(args.questions.read_text()), json.loads(args.identities.read_text()),
                              collection=args.collection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"pairs": len(manifest["pairs"]), "status": manifest["status"]}))


if __name__ == "__main__":
    main()
