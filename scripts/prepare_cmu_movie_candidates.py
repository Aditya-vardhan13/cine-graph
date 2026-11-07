#!/usr/bin/env python3
"""Prepare a local candidate-only manifest from the CMU Movie Summary Corpus.

This is a discovery aid, not an ingestion adapter: no plot text, Freebase IDs,
or derived facts are written to the manifest or to CineGraph's live catalog.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA = "cinegraph.cmu-movie-candidates/v1"
SOURCE = "CMU Movie Summary Corpus"
LICENSE = "CC BY-SA (corpus README; verify exact item terms before reuse)"


def _year(value: str) -> int | None:
    if not value:
        return None
    match = re.match(r"^(\d{4})", value.strip())
    year = int(match.group(1)) if match else None
    # Corpus metadata comes from 2012; dates outside cinema history through
    # that snapshot are anomalies, not values to propagate downstream.
    return year if year is not None and 1888 <= year <= 2012 else None


def _english_status(raw: str) -> str:
    try:
        languages: Any = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return "unknown"
    if not isinstance(languages, dict):
        return "unknown"
    names = [str(value).casefold() for value in languages.values()]
    if any("english language" in value for value in names):
        return "yes"
    return "no" if names else "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _plot_page_ids(path: Path) -> tuple[set[str], int, int]:
    page_ids: set[str] = set()
    rows = malformed = 0
    with path.open("r", encoding="utf-8", errors="strict") as stream:
        for line in stream:
            rows += 1
            page_id, separator, summary = line.rstrip("\n").partition("\t")
            if not separator or not page_id.isdigit() or not summary.strip():
                malformed += 1
                continue
            page_ids.add(page_id)
    return page_ids, rows, malformed


def prepare(metadata_path: Path, plots_path: Path, output_path: Path) -> dict[str, Any]:
    plot_ids, plot_rows, malformed_plot_rows = _plot_page_ids(plots_path)
    fields = Counter()
    seen: set[str] = set()
    duplicates: list[str] = []
    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []

    with metadata_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        for row_number, row in enumerate(reader, start=1):
            fields["metadata_rows"] += 1
            if len(row) != 9:
                fields["malformed_metadata_rows"] += 1
                quarantined.append({"row": row_number, "reason": "expected_9_columns"})
                continue
            page_id, _freebase_id, title, release_date, _box_office, _runtime, languages, _countries, _genres = row
            if not page_id.isdigit() or not title.strip():
                fields["invalid_identity_rows"] += 1
                quarantined.append({"row": row_number, "reason": "missing_page_id_or_title"})
                continue
            if page_id in seen:
                duplicates.append(page_id)
                continue
            seen.add(page_id)
            language_status = _english_status(languages)
            has_summary = page_id in plot_ids
            year = _year(release_date)
            fields[f"english_status_{language_status}"] += 1
            fields["release_year_valid"] += int(year is not None)
            fields["release_year_missing_or_anomalous"] += int(year is None)
            fields["with_plot_summary"] += int(has_summary)
            fields["without_plot_summary"] += int(not has_summary)
            candidates.append({
                "wikipedia_page_id": int(page_id),
                "title_candidate": title.strip(),
                "release_year_candidate": year,
                "release_year_status": "candidate_valid" if year is not None else "missing_or_anomalous",
                "english_language_candidate": language_status,
                "historical_plot_summary_available": has_summary,
                "identity_status": "unverified_candidate",
                "current_wikipedia_capture_required": True,
                "wikidata_identity_verification_required": True,
                "product_ingestion_status": "not_ingested",
            })

    # Stable ranking makes the file convenient for operator review while
    # retaining every usable row; it does not rank artistic or product value.
    candidates.sort(key=lambda item: (
        item["english_language_candidate"] != "yes",
        not item["historical_plot_summary_available"],
        item["release_year_candidate"] is None,
        item["release_year_candidate"] or 0,
        item["title_candidate"].casefold(),
        item["wikipedia_page_id"],
    ))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": SCHEMA,
        "candidate_only": True,
        "source": {
            "name": SOURCE,
            "paper": "Bamman, O'Connor, Smith (ACL 2013), Learning Latent Personas of Film Characters",
            "source_page": "https://www.cs.cmu.edu/~ark/personas/",
            "corpus_readme": "https://www.cs.cmu.edu/~ark/personas/data/README.txt",
            "historical_basis": "English Wikipedia dump 2012-11-02; metadata extracted from Freebase 2012-11-04",
            "license_note": LICENSE,
            "usage_boundary": "Discovery and selection only; this manifest excludes plot text and Freebase identifiers. Verify current identity, source revision, license, and rights before any product ingestion.",
            "metadata_sha256": _sha256(metadata_path),
            "plot_file_sha256": _sha256(plots_path),
        },
        "counts": {
            **dict(fields),
            "plot_file_rows": plot_rows,
            "unique_plot_page_ids": len(plot_ids),
            "malformed_plot_rows": malformed_plot_rows,
            "duplicate_metadata_page_ids": len(duplicates),
            "quarantined_metadata_rows": len(quarantined),
            "candidate_rows": len(candidates),
        },
        "duplicate_page_ids": sorted(set(duplicates), key=int),
        "quarantined_rows": quarantined,
        "candidates": candidates,
    }
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--plots", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.metadata, args.plots, args.output)
    print(json.dumps({"output": str(args.output), "counts": report["counts"]}, indent=2))


if __name__ == "__main__":
    main()
