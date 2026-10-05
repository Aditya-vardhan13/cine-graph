"""Resumable operator run for verified enwiki revision chunks.

The input files are derived from retained Wikidata sitelinks. Each chunk is a
separate committed source run; an interruption never requires recrawling a
completed chunk. This process is never invoked by web/API startup or tests.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.db import SessionLocal
from app.services.wikipedia_raw import (
    ingest_title_year_entries, read_manifest, request_interval_seconds,
)
from app.services.wikipedia_research import (
    extract_passages, selected_qids_from_ingestion_manifests,
)


def listed_chunk_paths(manifest_dir: Path) -> list[Path]:
    coverage_path = manifest_dir / "coverage.json"
    if not coverage_path.is_file():
        raise ValueError("Manifest directory has no coverage.json")
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    paths = []
    for name in coverage.get("revision_job_manifests", []):
        candidate = Path(name)
        if not candidate.is_absolute() and not candidate.exists():
            candidate = manifest_dir / candidate.name
        if candidate.resolve().parent != manifest_dir.resolve() or not candidate.is_file():
            raise ValueError(f"Chunk manifest is missing or outside its directory: {name}")
        paths.append(candidate)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest verified enwiki narrative chunks")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--start-chunk", type=int, default=1)
    parser.add_argument("--max-chunks", type=int)
    args = parser.parse_args()
    try:
        paths = listed_chunk_paths(args.manifest_dir)
    except ValueError as exc:
        parser.error(str(exc))
    if not paths or args.start_chunk < 1:
        parser.error("No chunk manifests found or invalid start chunk")
    selected = paths[args.start_chunk - 1:]
    if args.max_chunks is not None:
        if args.max_chunks < 1:
            parser.error("--max-chunks must be positive")
        selected = selected[:args.max_chunks]
    prior = []
    if args.report.exists():
        prior = json.loads(args.report.read_text(encoding="utf-8")).get("chunks", [])
    completed = {item["manifest"] for item in prior if item.get("status") == "complete"}
    for index, path in enumerate(selected):
        uri = path.resolve().as_uri()
        if uri in completed:
            print(json.dumps({"skipped_completed": str(path)}), flush=True)
            continue
        if index:
            time.sleep(request_interval_seconds())
        entries, manifest_hash = read_manifest(path)
        with SessionLocal() as db:
            raw = ingest_title_year_entries(db, entries, manifest_uri=uri)
            qids = selected_qids_from_ingestion_manifests(db, [uri])
            extracted = []
            for qid in qids:
                result = extract_passages(db, qid)
                extracted.append({"qid": qid, "passages_created": result["passages_created"]})
        item = {"manifest": uri, "manifest_sha256": manifest_hash,
                "status": "complete", "raw": raw,
                "films_with_passages": len(extracted),
                "passages_created": sum(row["passages_created"] for row in extracted)}
        prior.append(item)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"chunks": prior}, indent=2), encoding="utf-8")
        print(json.dumps({"chunk": str(path), "raw": raw,
                          "films_with_passages": item["films_with_passages"],
                          "passages_created": item["passages_created"]}), flush=True)


if __name__ == "__main__":
    main()
