"""Build a minimal, reproducible title/year target list from the local CSV."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from typing import Any


SCHEMA = "cinegraph.english-catalog-target-candidates/v1"
REQUIRED_COLUMNS = {"Series_Title", "Released_Year"}


def build_english_catalog_target(csv_bytes: bytes, *, expected_count: int = 1000) -> dict[str, Any]:
    """Freeze all ranked rows without importing unrelated source fields.

    The CSV contributes only row order, title and release-year candidate. It is
    not treated as a current ranking, identity authority, or license grant.
    Duplicate title/year rows are deliberately retained and annotated.
    """
    if expected_count < 1:
        raise ValueError("expected_count must be positive")
    try:
        text = csv_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("Candidate CSV is missing required title/year columns")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Candidate input must be valid UTF-8 CSV") from exc
    if len(rows) < expected_count:
        raise ValueError(f"Expected at least {expected_count} data rows; found {len(rows)}")

    parsed: list[dict[str, Any]] = []
    for rank, row in enumerate(rows[:expected_count], start=1):
        title = (row.get("Series_Title") or "").strip()
        year_raw = (row.get("Released_Year") or "").strip()
        if not title or title == "Series_Title":
            raise ValueError(f"Candidate row {rank} has an invalid title")
        year = int(year_raw) if re.fullmatch(r"\d{4}", year_raw) else None
        if year is None:
            raise ValueError(f"Candidate row {rank} has an invalid four-digit release year")
        parsed.append({
            "selection_rank": rank,
            "input_row": rank,
            "title": title,
            "release_year_candidate": year,
            "catalog_identity_status": "unresolved",
        })

    seen: dict[tuple[str, int], int] = {}
    for item in parsed:
        key = (" ".join(item["title"].casefold().split()), item["release_year_candidate"])
        prior_rank = seen.get(key)
        if prior_rank is not None:
            item["duplicate_candidate_of_rank"] = prior_rank
            item["catalog_identity_status"] = "duplicate_candidate_review"
        else:
            seen[key] = item["selection_rank"]

    title_counts = Counter(" ".join(item["title"].casefold().split()) for item in parsed)
    excluded_rows = []
    for input_row, row in enumerate(rows[expected_count:], start=expected_count + 1):
        title = (row.get("Series_Title") or "").strip()
        year_raw = (row.get("Released_Year") or "").strip()
        year = int(year_raw) if re.fullmatch(r"\d{4}", year_raw) else None
        excluded_rows.append({"input_row": input_row, "title": title, "release_year_candidate": year})
    return {
        "schema": SCHEMA,
        "selection_rule": f"first {expected_count} data rows in source order; preserve duplicates",
        "input_source": "project-local imdb_top_1000.csv",
        "input_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "input_row_count": len(rows),
        "candidate_count": len(parsed),
        "catalog_identity_resolved": False,
        "official_or_current_ranking_claim": False,
        "source_fields_used": ["Series_Title", "Released_Year", "row order"],
        "candidates": parsed,
        "repeated_title_groups_different_years_possible": sum(
            1 for count in title_counts.values() if count > 1
        ),
        "out_of_scope_rows_after_selection": excluded_rows,
        "caution": (
            "Selection input only. Titles and years are unresolved candidates; this is not an "
            "official/current ranking, a verified catalog list, or permission to reuse other CSV fields."
        ),
    }


def validate_english_catalog_target(
    manifest: dict[str, Any], csv_bytes: bytes, *, expected_count: int = 1000,
) -> dict[str, Any]:
    """Rebuild and compare a target manifest against its exact input bytes."""
    expected = build_english_catalog_target(csv_bytes, expected_count=expected_count)
    if manifest != expected:
        raise ValueError("Target manifest differs from deterministic rows or input fingerprint")
    return {
        "valid": True,
        "candidate_count": expected["candidate_count"],
        "input_row_count": expected["input_row_count"],
        "input_sha256": expected["input_sha256"],
        "out_of_scope_rows_after_selection": expected["out_of_scope_rows_after_selection"],
        "catalog_identity_resolved": False,
    }
