"""Freeze an English-first catalog pilot without merging or authorizing source data."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from typing import Any

from app.services.catalog_pilot_manifest import normalize_title


def _film_years(film: dict[str, Any]) -> set[str]:
    years = {str(year) for year in film.get("release_years_from_resolved_events", [])}
    release_date = film.get("release_date")
    if isinstance(release_date, str) and len(release_date) >= 4:
        years.add(release_date[:4])
    return years


def build_english_catalog_pilot(
    csv_bytes: bytes,
    readiness_bytes: bytes,
    *,
    expected_count: int = 100,
) -> dict[str, Any]:
    """Select the first N unique exact-title/year English catalog candidates.

    The input list supplies candidate ordering only. A selected row is a
    membership candidate, not an independently verified identity or license
    grant. Non-English and unclassified works are skipped, never re-labeled.
    """
    if expected_count < 1:
        raise ValueError("expected_count must be positive")
    try:
        input_rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        readiness = json.loads(readiness_bytes)
    except (UnicodeDecodeError, csv.Error, json.JSONDecodeError) as exc:
        raise ValueError("Pilot inputs must be valid UTF-8 CSV and JSON") from exc
    films = readiness.get("films") if isinstance(readiness, dict) else None
    if not isinstance(films, list):
        raise ValueError("Readiness report must contain a films array")

    english_index: dict[tuple[str, str], dict[str, tuple[dict[str, Any], str | None]]] = {}
    any_language_index: dict[tuple[str, str], set[str]] = {}
    for film in films:
        if not isinstance(film, dict) or not isinstance(film.get("film_id"), str):
            raise ValueError("Readiness report contains a film without a stable film_id")
        language = film.get("language")
        if not isinstance(language, str):
            language = "und"
        aliases = film.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError("Film aliases must be an array")
        for year in _film_years(film):
            for title, alias in [(film.get("title"), None)] + [
                (item.get("value"), item.get("value"))
                for item in aliases if isinstance(item, dict)
            ]:
                if not isinstance(title, str) or not title.strip():
                    continue
                key = (normalize_title(title), year)
                any_language_index.setdefault(key, set()).add(language)
                if language == "en":
                    candidates = english_index.setdefault(key, {})
                    existing = candidates.get(film["film_id"])
                    # Prefer the canonical title if both it and an alias match.
                    if existing is None or (existing[1] is not None and alias is None):
                        candidates[film["film_id"]] = (film, alias)

    selected: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    used_film_ids: set[str] = set()
    scanned_rows = 0
    for input_rank, row in enumerate(input_rows, 1):
        scanned_rows = input_rank
        title = (row.get("Series_Title") or "").strip()
        try:
            year = str(int(row.get("Released_Year", "")))
        except (TypeError, ValueError):
            skipped["invalid_input_year"] += 1
            continue
        key = (normalize_title(title), year)
        candidates = english_index.get(key, {})
        if len(candidates) > 1:
            skipped["ambiguous_english_title_year"] += 1
            continue
        if not candidates:
            languages = any_language_index.get(key, set())
            skipped["non_english_or_unclassified_match" if languages else "no_exact_title_year_match"] += 1
            continue
        film_id, (film, matched_alias) = next(iter(candidates.items()))
        if film_id in used_film_ids:
            skipped["duplicate_catalog_film"] += 1
            continue
        used_film_ids.add(film_id)
        selected.append({
            "selection_rank": len(selected) + 1,
            "input_rank": input_rank,
            "input_title": title,
            "input_year": int(year),
            "catalog_match": "exact_title_year" if matched_alias is None else "exact_alias_year",
            "matched_alias": matched_alias,
            "catalog_film_id": film_id,
            "catalog_title": film["title"],
            "wikidata_id": film.get("wikidata_id"),
            "catalog_language": "en",
            "release_years_from_resolved_events": sorted(_film_years(film)),
            "gaps": sorted(film.get("gaps", [])),
        })
        if len(selected) == expected_count:
            break

    if len(selected) != expected_count:
        raise ValueError(
            f"Only {len(selected)} unique exact-title/year English candidates found; "
            f"need {expected_count}"
        )
    return {
        "version": "english-catalog-pilot-v1",
        "selection_policy": "first unique exact-title/year catalog candidates whose recorded language is en",
        "selection_source": "local candidate list; selection order only, no source-field reuse authorization",
        "candidate_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "readiness_report_sha256": hashlib.sha256(readiness_bytes).hexdigest(),
        "expected_count": expected_count,
        "film_count": len(selected),
        "input_rows_scanned": scanned_rows,
        "skipped_input_rows_before_completion": dict(sorted(skipped.items())),
        "unique_catalog_film_count": len(used_film_ids),
        "films": selected,
        "caution": (
            "Candidate membership only. Exact title/year and a recorded en code "
            "do not independently verify identity, source accuracy, rights, or completeness."
        ),
    }


def validate_english_catalog_pilot(
    pilot: dict[str, Any],
    csv_bytes: bytes,
    readiness_bytes: bytes,
    *,
    expected_count: int = 100,
) -> dict[str, Any]:
    """Rebuild and compare the manifest to its exact hashed inputs."""
    expected = build_english_catalog_pilot(
        csv_bytes, readiness_bytes, expected_count=expected_count,
    )
    if pilot != expected:
        raise ValueError("English pilot differs from deterministic selection or input fingerprints")
    return {
        "valid": True,
        "film_count": expected["film_count"],
        "input_rows_scanned": expected["input_rows_scanned"],
        "selection_source_sha256": expected["candidate_csv_sha256"],
        "readiness_report_sha256": expected["readiness_report_sha256"],
        "identity_state_counts": dict(sorted(Counter(
            film["catalog_match"] for film in expected["films"]
        ).items())),
        "caution": "Structural reproducibility does not prove identity truth, source quality, or reuse rights.",
    }
