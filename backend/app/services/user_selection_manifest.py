"""Turn a user-provided title/year CSV into a private, identifier-resolution manifest.

This adapter deliberately reads only a title and release-year column. It does
not copy provider ratings, votes, synopsis, gross, posters, certificates, or
credits into CineGraph. The input file remains local and ignored by Git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

SCHEMA = "cinegraph.user-selection-manifest/v1"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_title_year_rows(path: Path, limit: int | None = None) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        required = {"Series_Title", "Released_Year"}
        if not rows.fieldnames or not required.issubset(rows.fieldnames):
            raise ValueError("The selection CSV must contain Series_Title and Released_Year columns.")
        entries: list[dict[str, object]] = []
        for row in rows:
            title = (row.get("Series_Title") or "").strip()
            year_text = (row.get("Released_Year") or "").strip()
            if not title or not year_text.isdigit():
                continue
            entries.append({"position": len(entries) + 1, "title": title, "release_year": int(year_text)})
            if limit and len(entries) >= limit:
                break
    if not entries:
        raise ValueError("The selection CSV contained no usable title/year rows.")
    return entries


def build_manifest(path: Path, limit: int | None = None) -> dict:
    return {
        "schema": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_type": "user-provided private title/year manifest",
        "input": {
            "local_filename": path.name,
            "sha256": file_hash(path),
            "fields_used": ["Series_Title", "Released_Year"],
            "fields_excluded": "all other input columns",
        },
        "entries": read_title_year_rows(path, limit=limit),
    }


def write_manifest(manifest: dict, output: Path) -> tuple[Path, str]:
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    return output.resolve(), hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a private title/year selection manifest.")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (Path(get_settings().raw_snapshot_root).parent / "manifests" / "user-title-year-selection.json")
    path, digest = write_manifest(build_manifest(args.csv_path, args.limit), output)
    print({"path": str(path), "sha256": digest})


if __name__ == "__main__":
    main()
