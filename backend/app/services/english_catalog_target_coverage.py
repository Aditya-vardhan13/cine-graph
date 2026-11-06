"""Summarize per-film readiness for a frozen title target without DB writes."""
from __future__ import annotations

from collections import Counter
from typing import Any


def build_english_catalog_target_coverage(
    target: dict[str, Any], identity: dict[str, Any], imdb_review: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if target.get("candidate_count") != len(target.get("candidates", [])):
        raise ValueError("Target candidate count is inconsistent")
    readiness_rows = readiness.get("films")
    if not isinstance(readiness_rows, list):
        raise ValueError("Readiness report must contain a films array")
    readiness_by_id: dict[str, dict[str, Any]] = {}
    for row in readiness_rows:
        if not isinstance(row, dict) or not isinstance(row.get("film_id"), str):
            raise ValueError("Readiness rows must have a string film_id")
        if row["film_id"] in readiness_by_id:
            raise ValueError(f"Readiness report repeats film_id {row['film_id']}")
        readiness_by_id[row["film_id"]] = row

    def ranked_rows(report: dict[str, Any], label: str) -> dict[int, dict[str, Any]]:
        rows = report.get("candidates")
        if not isinstance(rows, list):
            raise ValueError(f"{label} report must contain a candidates array")
        result: dict[int, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("selection_rank"), int):
                raise ValueError(f"{label} rows must have an integer selection_rank")
            rank = row["selection_rank"]
            if rank in result:
                raise ValueError(f"{label} report repeats selection rank {rank}")
            result[rank] = row
        return result

    target_ranks = [row.get("selection_rank") for row in target.get("candidates", [])]
    expected_ranks = list(range(1, target["candidate_count"] + 1))
    if target_ranks != expected_ranks:
        raise ValueError("Target rows must have unique contiguous selection ranks")
    identity_by_rank = ranked_rows(identity, "Identity")
    imdb_by_rank = ranked_rows(imdb_review, "IMDb review")
    if set(identity_by_rank) != set(expected_ranks):
        raise ValueError("Identity audit does not cover every target rank")
    if not set(imdb_by_rank).issubset(set(expected_ranks)):
        raise ValueError("IMDb review contains a rank outside the target")

    items: list[dict[str, Any]] = []
    mapping_states: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    language_admission: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    for source in target["candidates"]:
        rank = source["selection_rank"]
        identity_row = identity_by_rank[rank]
        candidate_rows = identity_row.get("catalog_candidates", [])
        mapping_basis = identity_row.get("identity_candidate_status")
        if not candidate_rows:
            imdb_row = imdb_by_rank.get(rank)
            exact_hits = [hit for hit in (imdb_row or {}).get("imdb_candidates", [])
                          if hit.get("title_exact_after_normalization") is True
                          and hit.get("year_exact") is True]
            crosslinked = {
                candidate["film_id"]: candidate
                for hit in exact_hits
                for candidate in hit.get("catalog_identity_candidates", [])
                if isinstance(candidate.get("film_id"), str)
            }
            candidate_rows = list(crosslinked.values())
            mapping_basis = "imdb_external_id_candidate_review_required" if candidate_rows else mapping_basis
        unique = {row.get("film_id"): row for row in candidate_rows if row.get("film_id")}
        if len(unique) == 1:
            candidate = next(iter(unique.values()))
            film = readiness_by_id.get(candidate["film_id"])
            if film is None:
                item = {"selection_rank": rank, "title": source["title"],
                        "year_candidate": source["release_year_candidate"],
                        "mapping_status": "candidate_missing_from_readiness", "mapping_basis": mapping_basis}
            else:
                language = film.get("language") or "und"
                categories = set(film.get("narrative_categories", []))
                rights = film.get("narrative_use_coverage", {})
                credits = film.get("credits_by_role", {})
                assertions = film.get("resolved_assertions", {})
                character_credit_count = sum(
                    value.get("with_character", 0)
                    for value in credits.values() if isinstance(value, dict)
                )
                item = {
                    "selection_rank": rank,
                    "title": source["title"],
                    "year_candidate": source["release_year_candidate"],
                    "mapping_status": "candidate_review_required",
                    "mapping_basis": mapping_basis,
                    "catalog_film_id": film["film_id"],
                    "catalog_title": film["title"],
                    "wikidata_id": film.get("wikidata_id"),
                    "catalog_language": language,
                    "release_date_present": bool(film.get("release_date")),
                    "release_event_year_count": len(film.get("release_years_from_resolved_events", [])),
                    "runtime_present": bool(film.get("runtime_minutes")),
                    "narrative_categories": sorted(categories),
                    "credits_by_role": credits,
                    "legacy_credit_rows_with_character_field": character_credit_count,
                    "resolved_assertion_counts": assertions,
                    "source_snapshot_count": film.get("source_snapshots", 0),
                    "semantic_rights_eligible_snapshot_count": rights.get("eligible", 0),
                    "embedding_vector_count": film.get("embedding_vectors", 0),
                    "semantically_eligible_embedding_vector_count": film.get("semantically_eligible_embedding_vectors", 0),
                }
                languages[language] += 1
        elif len(unique) > 1:
            item = {"selection_rank": rank, "title": source["title"],
                    "year_candidate": source["release_year_candidate"],
                    "mapping_status": "ambiguous_catalog_candidates",
                    "candidate_film_ids": sorted(unique), "mapping_basis": mapping_basis}
        else:
            item = {"selection_rank": rank, "title": source["title"],
                    "year_candidate": source["release_year_candidate"],
                    "mapping_status": "no_catalog_candidate", "mapping_basis": mapping_basis}

        is_candidate = item["mapping_status"] == "candidate_review_required"
        language = item.get("catalog_language") if is_candidate else None
        if not is_candidate:
            admission = "identity_unresolved"
        elif language == "en":
            admission = "english_candidate_review_required"
        elif language in {"und", "mul", None}:
            admission = "language_unresolved"
        else:
            admission = "non_english_candidate"
        item["english_target_status"] = admission
        language_admission[admission] += 1
        is_evidence_ready = bool(
            is_candidate
            and item["semantic_rights_eligible_snapshot_count"] > 0
            and item["narrative_categories"]
        )
        is_indexed = bool(
            is_candidate and item["semantically_eligible_embedding_vector_count"] > 0
        )
        review_reasons: list[str] = []
        if not is_candidate:
            review_reasons.append(item["mapping_status"])
        else:
            review_reasons.append("identity_candidate_requires_review")
            if item["catalog_language"] in {"und", "mul"}:
                review_reasons.append("language_unresolved")
            elif item["catalog_language"] != "en":
                review_reasons.append("non_english_candidate")
            if item["source_snapshot_count"] == 0:
                review_reasons.append("narrative_source_missing")
            elif item["semantic_rights_eligible_snapshot_count"] == 0:
                review_reasons.append("source_rights_review_required")
            if not item["narrative_categories"]:
                review_reasons.append("narrative_sections_missing")
            if item["semantically_eligible_embedding_vector_count"] == 0:
                review_reasons.append("eligible_evidence_not_indexed")
        item["pipeline_stages"] = {
            "requested": True,
            "catalog_identity_candidate_resolved": is_candidate,
            "english_language_candidate": is_candidate and language == "en",
            "narrative_evidence_ready": is_evidence_ready,
            "semantically_indexed": is_indexed,
            "review_required": bool(review_reasons),
        }
        item["review_required_reasons"] = review_reasons
        for stage, reached in item["pipeline_stages"].items():
            if reached:
                stage_counts[stage] += 1
        mapping_states[item["mapping_status"]] += 1
        items.append(item)

    mapped = [item for item in items if item["mapping_status"] == "candidate_review_required"]
    category_counts = {
        category: sum(category in row["narrative_categories"] for row in mapped)
        for category in ("plot", "production", "reception", "themes", "legacy", "writing_craft")
    }
    return {
        "schema": "cinegraph.english-catalog-target-coverage/v3",
        "target_count": len(items),
        "catalog_candidate_mappings": len(mapped),
        "pipeline_stage_counts": dict(sorted(stage_counts.items())),
        "mapping_status_counts": dict(sorted(mapping_states.items())),
        "mapped_candidate_language_counts": dict(sorted(languages.items())),
        "english_target_status_counts": dict(sorted(language_admission.items())),
        "mapped_candidate_category_counts": category_counts,
        "mapped_candidate_counts": {
            "with_release_date": sum(row["release_date_present"] for row in mapped),
            "with_runtime": sum(row["runtime_present"] for row in mapped),
            "with_resolved_release_event_assertion": sum(row["resolved_assertion_counts"].get("release_event", 0) > 0 for row in mapped),
            "with_resolved_runtime_assertion": sum(row["resolved_assertion_counts"].get("runtime", 0) > 0 for row in mapped),
            "with_resolved_director_assertion": sum(row["resolved_assertion_counts"].get("director", 0) > 0 for row in mapped),
            "with_resolved_writer_assertion": sum(row["resolved_assertion_counts"].get("writer", 0) > 0 for row in mapped),
            "with_resolved_cast_assertion": sum(row["resolved_assertion_counts"].get("cast", 0) > 0 for row in mapped),
            "with_resolved_character_assertion": sum(row["resolved_assertion_counts"].get("character", 0) > 0 for row in mapped),
            "with_any_source_snapshot": sum(row["source_snapshot_count"] > 0 for row in mapped),
            "with_any_semantically_eligible_snapshot": sum(row["semantic_rights_eligible_snapshot_count"] > 0 for row in mapped),
            "with_any_embedding": sum(row["embedding_vector_count"] > 0 for row in mapped),
            "with_any_eligible_embedding": sum(row["semantically_eligible_embedding_vector_count"] > 0 for row in mapped),
            "with_any_legacy_character_credit_label": sum(row["legacy_credit_rows_with_character_field"] > 0 for row in mapped),
        },
        "films": items,
        "caution": (
            "Readiness counts are presence indicators from one local report. Candidate mappings—including "
            "IMDb external-ID crosslinks—are not verified identity decisions. No corpus data was changed."
        ),
    }


def render_english_catalog_target_coverage(report: dict[str, Any]) -> str:
    """Render concise, field-specific coverage without exposing narrative prose."""
    counts = report["mapped_candidate_counts"]
    categories = report["mapped_candidate_category_counts"]
    mapped_count = report["catalog_candidate_mappings"]
    lines = [
        "# Local candidate coverage: supplied 1,000-title list",
        "",
        "This is a read-only join to catalog readiness. The input list is not certified as an English-only set or a current IMDb ranking. Candidate identity matches are not reviewed facts. This report does not establish a 1,000-film English collection.",
        "",
        f"- Target rows: **{report['target_count']}**",
        f"- Unique catalog candidate mappings: **{mapped_count}**",
        f"- Mapping states: {report['mapping_status_counts']}",
        f"- Language labels among mapped candidates: {report['mapped_candidate_language_counts']}",
        f"- English-target admission states: {report['english_target_status_counts']}",
        "",
        "## Intake pipeline gates",
        "",
        "These are explicit counts of reached gates, not mutually exclusive statuses. A unique catalog mapping remains an identity candidate until reviewed.",
        "",
        "| Gate | Films | Denominator |",
        "| --- | ---: | ---: |",
        f"| Requested | {report['pipeline_stage_counts'].get('requested', 0)} | {report['target_count']} candidates |",
        f"| Unique catalog identity candidate resolved (unreviewed) | {report['pipeline_stage_counts'].get('catalog_identity_candidate_resolved', 0)} | {report['target_count']} candidates |",
        f"| English-language identity candidates (still unreviewed) | {report['pipeline_stage_counts'].get('english_language_candidate', 0)} | {report['target_count']} candidates |",
        f"| Narrative evidence ready for semantic use | {report['pipeline_stage_counts'].get('narrative_evidence_ready', 0)} | {report['target_count']} candidates |",
        f"| Semantically indexed | {report['pipeline_stage_counts'].get('semantically_indexed', 0)} | {report['target_count']} candidates |",
        f"| Review required | {report['pipeline_stage_counts'].get('review_required', 0)} | {report['target_count']} candidates |",
        "",
        "| Coverage indicator | Films | Denominator |",
        "| --- | ---: | ---: |",
        f"| Has plot section | {categories['plot']} | {mapped_count} mapped candidates |",
        f"| Has production section | {categories['production']} | {mapped_count} mapped candidates |",
        f"| Has reception section | {categories['reception']} | {mapped_count} mapped candidates |",
        f"| Has themes section | {categories['themes']} | {mapped_count} mapped candidates |",
        f"| Has legacy section | {categories['legacy']} | {mapped_count} mapped candidates |",
        f"| Has writing/craft section | {categories['writing_craft']} | {mapped_count} mapped candidates |",
        f"| Has legacy release date | {counts['with_release_date']} | {mapped_count} mapped candidates |",
        f"| Has any resolved sourced release-event assertion | {counts['with_resolved_release_event_assertion']} | {mapped_count} mapped candidates |",
        f"| Has runtime | {counts['with_runtime']} | {mapped_count} mapped candidates |",
        f"| Has any resolved sourced runtime assertion | {counts['with_resolved_runtime_assertion']} | {mapped_count} mapped candidates |",
        f"| Has director / writer / cast assertion | {counts['with_resolved_director_assertion']} / {counts['with_resolved_writer_assertion']} / {counts['with_resolved_cast_assertion']} | {mapped_count} mapped candidates |",
        f"| Has any resolved character assertion | {counts['with_resolved_character_assertion']} | {mapped_count} mapped candidates |",
        f"| Has any semantic-use-eligible source snapshot | {counts['with_any_semantically_eligible_snapshot']} | {mapped_count} mapped candidates |",
        f"| Has any eligible embedding vector | {counts['with_any_eligible_embedding']} | {mapped_count} mapped candidates |",
        f"| Has any character label in legacy credit rows | {counts['with_any_legacy_character_credit_label']} | {mapped_count} mapped candidates |",
        "",
        "A section/vector/source count does not establish accuracy, completeness, legal clearance, or relevance to a writing question. Inspect the per-film JSON rows and source evidence before selecting an ingestion batch.",
    ]
    return "\n".join(lines) + "\n"
