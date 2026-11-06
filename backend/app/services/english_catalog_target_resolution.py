"""Offline exact title/year identity-candidate audit for the frozen target."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from app.services.catalog_pilot_manifest import normalize_title
from app.services.english_catalog_target import SCHEMA as TARGET_SCHEMA


def _film_years(film: dict[str, Any]) -> set[int]:
    years: set[int] = set()
    for value in film.get("release_years_from_resolved_events", []):
        try:
            years.add(int(value))
        except (TypeError, ValueError):
            continue
    release_date = film.get("release_date")
    if isinstance(release_date, str) and len(release_date) >= 4:
        try:
            years.add(int(release_date[:4]))
        except ValueError:
            pass
    return years


def resolve_english_catalog_target(
    target: dict[str, Any], readiness: dict[str, Any], *,
    target_bytes: bytes, readiness_bytes: bytes,
) -> dict[str, Any]:
    """Join candidates to one read-only readiness snapshot, without writes.

    Exact normalized title/year matches are candidate identity evidence only;
    aliases, language classifications and release events still require review.
    No fuzzy matching or external-source lookup is performed.
    """
    if target.get("schema") != TARGET_SCHEMA or target.get("candidate_count") != len(target.get("candidates", [])):
        raise ValueError("Unsupported or inconsistent target candidate manifest")
    films = readiness.get("films")
    if not isinstance(films, list):
        raise ValueError("Readiness report must contain a films array")

    canonical: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    aliases: dict[tuple[str, int], dict[str, tuple[dict[str, Any], str]]] = {}
    for film in films:
        if not isinstance(film, dict) or not isinstance(film.get("film_id"), str):
            raise ValueError("Readiness report has an entry without film_id")
        title = film.get("title")
        if isinstance(title, str) and title.strip():
            for year in _film_years(film):
                canonical.setdefault((normalize_title(title), year), {})[film["film_id"]] = film
        for alias in film.get("aliases", []):
            if not isinstance(alias, dict) or not isinstance(alias.get("value"), str):
                continue
            for year in _film_years(film):
                key = (normalize_title(alias["value"]), year)
                aliases.setdefault(key, {})[film["film_id"]] = (film, alias["value"])

    audited: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    for item in target["candidates"]:
        title = item["title"]
        year = item["release_year_candidate"]
        key = (normalize_title(title), year)
        exact = canonical.get(key, {})
        alias_hits = aliases.get(key, {}) if not exact else {}
        hits = exact or alias_hits
        if len(hits) > 1:
            status = "ambiguous_exact_title_year" if exact else "ambiguous_exact_alias_year"
        elif exact:
            status = "exact_title_year_candidate"
        elif alias_hits:
            status = "exact_alias_year_candidate"
        else:
            status = "unmatched_exact_title_year"
        candidate_rows = []
        for film_id, value in sorted(hits.items()):
            film, matched_alias = value if isinstance(value, tuple) else (value, None)
            candidate_rows.append({
                "film_id": film_id,
                "catalog_title": film.get("title"),
                "wikidata_id": film.get("wikidata_id"),
                "catalog_language": film.get("language") or "und",
                "matched_alias": matched_alias,
                "release_years_from_resolved_events": sorted(_film_years(film)),
            })
        audited.append({
            "selection_rank": item["selection_rank"],
            "input_title": title,
            "input_year": year,
            "identity_candidate_status": status,
            "catalog_candidates": candidate_rows,
        })
        statuses[status] += 1

    return {
        "schema": "cinegraph.english-catalog-target-identity-audit/v1",
        "read_only": True,
        "target_sha256": hashlib.sha256(target_bytes).hexdigest(),
        "readiness_sha256": hashlib.sha256(readiness_bytes).hexdigest(),
        "target_count": len(audited),
        "identity_candidate_status_counts": dict(sorted(statuses.items())),
        "candidates": audited,
        "caution": (
            "Offline exact title/year joins are candidate matches, not reviewed identity facts. "
            "This audit writes no film, alias, assertion, source or rights rows."
        ),
    }
