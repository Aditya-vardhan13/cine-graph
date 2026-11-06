"""Classify IMDb title-index hits as identity-review leads, never resolutions."""
from __future__ import annotations

from collections import Counter
import re
from typing import Any

from app.services.catalog_pilot_manifest import normalize_title


def build_imdb_identity_review(
    identity_audit: dict[str, Any], readiness: dict[str, Any],
    search_results_by_rank: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Join local IMDb search candidates to existing catalog IMDb IDs.

    IMDb's local data is non-commercial. The returned artifact is strictly a
    local identity-review aid; it does not publish or approve IMDb-sourced data.
    """
    if identity_audit.get("schema") != "cinegraph.english-catalog-target-identity-audit/v1":
        raise ValueError("Unsupported English catalog identity audit")
    catalog_by_imdb: dict[str, dict[str, dict[str, Any]]] = {}
    for film in readiness.get("films", []):
        for imdb_id in film.get("resolved_imdb_ids", []):
            catalog_by_imdb.setdefault(imdb_id, {})[film["film_id"]] = film

    review_rows: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    for audited in identity_audit.get("candidates", []):
        if audited.get("identity_candidate_status") not in {
            "unmatched_exact_title_year", "ambiguous_exact_title_year", "ambiguous_exact_alias_year",
        }:
            continue
        rank = audited["selection_rank"]
        hits = search_results_by_rank.get(rank, [])
        candidates = []
        for hit in hits:
            tconst = hit.get("tconst")
            if not isinstance(tconst, str) or not re.fullmatch(r"tt\d{7,10}", tconst):
                raise ValueError(f"IMDb candidate for target rank {rank} has invalid title ID")
            try:
                hit_year = int(hit["year"]) if hit.get("year") is not None else None
            except (TypeError, ValueError):
                hit_year = None
            title = hit.get("title") if isinstance(hit.get("title"), str) else ""
            same_title = bool(title) and normalize_title(title) == normalize_title(audited["input_title"])
            exact_year = hit_year == audited["input_year"]
            linked = catalog_by_imdb.get(tconst, {})
            candidates.append({
                "tconst": tconst,
                "imdb_title_candidate": title,
                "imdb_year_candidate": hit_year,
                "title_exact_after_normalization": same_title,
                "year_exact": exact_year,
                "search_score": hit.get("score"),
                "catalog_identity_candidates": [
                    {"film_id": film_id, "catalog_title": film.get("title"),
                     "wikidata_id": film.get("wikidata_id")}
                    for film_id, film in sorted(linked.items())
                ],
            })
        strong = [item for item in candidates if item["title_exact_after_normalization"] and item["year_exact"]]
        strong_tconsts = {item["tconst"] for item in strong}
        linked_ids = {
            row["film_id"] for item in strong for row in item["catalog_identity_candidates"]
        }
        if not strong:
            status = "no_exact_imdb_title_year_candidate"
        elif len(strong_tconsts) > 1:
            status = "ambiguous_exact_imdb_title_year_candidates"
        elif len(linked_ids) == 1:
            status = "unique_exact_imdb_crosslink_candidate_review_required"
        elif len(linked_ids) > 1:
            status = "imdb_candidate_links_to_multiple_catalog_films"
        else:
            status = "unique_exact_imdb_candidate_without_catalog_crosslink"
        statuses[status] += 1
        review_rows.append({
            "selection_rank": rank,
            "input_title": audited["input_title"],
            "input_year": audited["input_year"],
            "upstream_identity_status": audited["identity_candidate_status"],
            "review_status": "review_required",
            "candidate_status": status,
            "imdb_candidates": candidates,
        })

    if set(search_results_by_rank) - {row["selection_rank"] for row in review_rows}:
        raise ValueError("IMDb search results include target rows outside the review queue")
    return {
        "schema": "cinegraph.english-catalog-target-imdb-review/v1",
        "read_only": True,
        "review_queue_count": len(review_rows),
        "candidate_status_counts": dict(sorted(statuses.items())),
        "candidates": review_rows,
        "source_policy": "Local IMDb datasets are non-commercial; use only as local identity-review aid.",
        "caution": (
            "A matching local IMDb title/year or catalog external identifier is a lead, not a reviewed "
            "identity decision and grants no permission to publish IMDb fields."
        ),
    }
