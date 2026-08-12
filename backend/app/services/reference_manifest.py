"""Create a versioned, legal selection manifest before raw source collection."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.services.english_reference_shelf import Candidate, fetch_reference_candidates

MANIFEST_SCHEMA = "cinegraph.selection-manifest/v1"
SELECTION_METHOD = "year-balanced English-language Wikidata films ordered by cross-language sitelink coverage"


def payload(candidates: list[Candidate], start_year: int, end_year: int) -> dict:
    return {
        "schema": MANIFEST_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "collection": "CineGraph English 2000–2025 evaluation set",
        "not_a_claim": "This is not IMDb Top 100 and is not an artistic-quality ranking.",
        "source": {
            "name": "Wikidata",
            "license": "CC0 1.0",
            "reference": "https://www.wikidata.org/wiki/Wikidata:Database_download",
        },
        "selection": {
            "method": SELECTION_METHOD,
            "start_year": start_year,
            "end_year": end_year,
            "requested_count": len(candidates),
        },
        "entries": [
            {"position": index, "wikidata_id": item.wikidata_id, "wikidata_sitelink_count": item.sitelink_count}
            for index, item in enumerate(candidates, start=1)
        ],
    }


def write_manifest(document: dict, path: Path) -> tuple[Path, str]:
    encoded = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return path.resolve(), hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a source-backed CineGraph evaluation manifest.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (Path(get_settings().raw_snapshot_root).parent / "manifests" / "english-2000-2025-evaluation-100.json")
    candidates = fetch_reference_candidates(args.limit, args.start_year, args.end_year)
    document = payload(candidates, args.start_year, args.end_year)
    path, digest = write_manifest(document, output)
    print({"path": str(path), "sha256": digest, "entries": len(candidates)})


if __name__ == "__main__":
    main()
