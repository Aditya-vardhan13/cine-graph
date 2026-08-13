"""Create a source-auditable canonical manifest from a private seed manifest.

The seed file only chooses a working set.  This adapter permits a small,
reviewed set of corrections for abbreviations, transliterations and source
date disagreements, while retaining the original value alongside every
correction.  It never copies ratings, synopses or other provider fields.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.user_selection_manifest import write_manifest
from app.services.wikipedia_raw import read_manifest


def reconcile(manifest: Path, corrections: Path) -> dict[str, Any]:
    document = json.loads(manifest.read_text(encoding="utf-8"))
    entries, _ = read_manifest(manifest)
    patch_set = json.loads(corrections.read_text(encoding="utf-8"))
    if patch_set.get("schema") != "cinegraph.selection-reconciliation/v1":
        raise ValueError("Correction file must use cinegraph.selection-reconciliation/v1.")
    patches = {int(item["position"]): item for item in patch_set.get("corrections", [])}
    reconciled: list[dict[str, Any]] = []
    for entry in entries:
        patch = patches.get(int(entry["position"]))
        if not patch:
            reconciled.append(entry)
            continue
        required = {"wikidata_id", "wikipedia_title", "evidence_url"}
        if not required.issubset(patch):
            raise ValueError(f"Correction {entry['position']} lacks canonical identity evidence.")
        updated = {
            **entry,
            "seed_title": entry["title"],
            "seed_release_year": entry["release_year"],
            "wikidata_id": patch["wikidata_id"],
            "wikipedia_title": patch["wikipedia_title"],
            "selection_reconciliation": {
                "reason": patch.get("reason", "canonical title reconciliation"),
                "evidence_url": patch["evidence_url"],
            },
        }
        if patch.get("title"):
            updated["title"] = patch["title"]
        if patch.get("release_year"):
            updated["release_year"] = int(patch["release_year"])
        if patch.get("selection_year_evidence"):
            updated["selection_year_evidence"] = patch["selection_year_evidence"]
        reconciled.append(updated)
    return {
        **document,
        "entries": reconciled,
        "reconciliation": {
            "schema": patch_set["schema"],
            "corrections_applied": len(patches),
            "policy": "Every correction must carry a canonical Wikidata ID, an English Wikipedia page and a source URL; final identity/type/year remains independently audited from retained snapshots.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply reviewed canonical corrections to a private selection manifest.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("corrections", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    path, digest = write_manifest(reconcile(args.manifest, args.corrections), args.output)
    print({"path": str(path), "sha256": digest})


if __name__ == "__main__":
    main()
