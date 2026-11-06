"""Reconcile immutable source-capture batches to the frozen English pilot."""
from __future__ import annotations

from collections import Counter
from typing import Any


class EnglishPilotReconciliationError(ValueError):
    """A capture batch is incomplete or its identity does not match the pilot."""


def reconcile_english_pilot_captures(
    pilot: dict[str, Any], bundles: list[tuple[str, dict[str, Any], dict[str, Any]]], *,
    pilot_sha256: str,
) -> dict[str, Any]:
    """Verify audited capture bundles cover the exact pilot rows.

    Each bundle tuple is (local label, capture manifest, offline audit). A
    selection digest may differ when an older batch is reused, but only a
    complete row-by-row title/year/QID match can reconcile it. The differing
    digest remains visible in the result.
    """
    pilot_rows = pilot.get("films")
    expected_count = pilot.get("film_count")
    if (pilot.get("version") != "english-catalog-pilot-v1"
            or not isinstance(pilot_rows, list)
            or not isinstance(expected_count, int)
            or len(pilot_rows) != expected_count
            or expected_count < 1):
        raise EnglishPilotReconciliationError("Expected a valid frozen English catalog pilot manifest.")

    expected: dict[int, tuple[str, int, str]] = {}
    seen_qids: set[str] = set()
    seen_catalog_ids: set[str] = set()
    for row in pilot_rows:
        if not isinstance(row, dict):
            raise EnglishPilotReconciliationError("Pilot contains a malformed film row.")
        rank, title, year, qid = (
            row.get("selection_rank"), row.get("input_title"), row.get("input_year"), row.get("wikidata_id"),
        )
        if (not isinstance(rank, int) or rank < 1 or rank > expected_count
                or rank in expected or not isinstance(title, str) or not title.strip()
                or not isinstance(year, int) or not isinstance(qid, str)
                or not qid.startswith("Q") or not qid[1:].isdigit()
                or row.get("catalog_language") != "en"
                or row.get("catalog_match") not in {"exact_title_year", "exact_alias_year"}
                or qid in seen_qids
                or not isinstance(row.get("catalog_film_id"), str)
                or row["catalog_film_id"] in seen_catalog_ids):
            raise EnglishPilotReconciliationError("Pilot row lacks a unique exact English catalog identity.")
        seen_qids.add(qid)
        seen_catalog_ids.add(row["catalog_film_id"])
        expected[rank] = (title, year, qid)
    if set(expected) != set(range(1, expected_count + 1)):
        raise EnglishPilotReconciliationError("Pilot selection ranks are not contiguous.")

    selected: dict[int, dict[str, Any]] = {}
    batch_summaries: list[dict[str, Any]] = []
    for label, manifest, audit in bundles:
        if manifest.get("schema") != "cinegraph.catalog-pilot-capture/v1":
            raise EnglishPilotReconciliationError(f"{label}: unsupported capture manifest schema.")
        if (audit.get("schema") != "cinegraph.catalog-pilot-audit/v2"
                or audit.get("selection_sha256") != manifest.get("selection_sha256")
                or audit.get("identity_and_capture_pass") is not True
                or audit.get("audited_films") != audit.get("requested_films")
                or manifest.get("run_status") != "complete"):
            raise EnglishPilotReconciliationError(f"{label}: capture integrity audit did not pass.")
        audited_by_qid = {row.get("qid"): row for row in audit.get("films", [])}
        capture_rows = manifest.get("films")
        if not isinstance(capture_rows, list) or len(capture_rows) != audit["requested_films"]:
            raise EnglishPilotReconciliationError(f"{label}: capture manifest/audit counts disagree.")
        for row in capture_rows:
            rank = row.get("selection_rank")
            qid = row.get("qid")
            identity = expected.get(rank) if isinstance(rank, int) else None
            if (identity is None or rank in selected
                    or (row.get("title"), row.get("year"), qid) != identity
                    or row.get("identity_status") != "verified"
                    or row.get("wikipedia_status") != "captured"
                    or qid not in audited_by_qid):
                raise EnglishPilotReconciliationError(
                    f"{label}: captured row does not uniquely match its frozen English pilot rank."
                )
            audit_row = audited_by_qid[qid]
            if (audit_row.get("title"), audit_row.get("year"), audit_row.get("qid")) != (
                    identity[0], identity[1], identity[2]):
                raise EnglishPilotReconciliationError(f"{label}: audit identity disagrees for rank {rank}.")
            selected[rank] = {
                "rank": rank,
                "title": identity[0],
                "year": identity[1],
                "qid": qid,
                "batch": label,
                "wikipedia_revision": audit_row["wikipedia_revision"],
                "wikipedia_sha256": row["wikipedia_sha256"],
                "wikidata_revision": audit_row["wikidata_revision"],
                "wikidata_sha256": row["wikidata_sha256"],
                "passage_count": audit_row["passage_count"],
                "categories": audit_row["categories"],
                "wikidata_metadata": audit_row["wikidata_metadata"],
                "missing_content_categories": audit_row["missing_content_categories"],
            }
        batch_summaries.append({
            "label": label,
            "requested": audit["requested_films"],
            "selection_sha256": manifest["selection_sha256"],
            "selection_hash_matches_pilot": manifest["selection_sha256"] == pilot_sha256,
            "passages": audit["total_passages"],
            "raw_capture_bytes": audit["total_raw_capture_bytes"],
            "citation_marker_passages": audit["passages_with_citation_markers"],
            "wikidata_robots_sha256": audit.get("wikidata_robots_sha256"),
            "wikipedia_robots_sha256": audit.get("wikipedia_robots_sha256"),
            "capture_policy": manifest.get("capture_policy"),
        })

    if set(selected) != set(expected):
        missing = sorted(set(expected) - set(selected))
        raise EnglishPilotReconciliationError(f"Capture bundles do not cover pilot ranks: {missing}.")

    coverage: dict[str, dict[str, int]] = {}
    for category in ("plot", "production", "reception", "themes_analysis", "legacy"):
        with_section = sum(bool(row["categories"][category]) for row in selected.values())
        coverage[category] = {"films_with_section": with_section,
                              "films_missing_section": expected_count - with_section}

    totals: Counter[str] = Counter()
    cast_with_character = 0
    cast_without_character = 0
    territory_dates = referenced_dates = runtime_value_films = 0
    for row in selected.values():
        metadata = row["wikidata_metadata"]
        for field, count in metadata["value_statement_counts"].items():
            totals[f"{field}_statements"] += count
            totals[f"{field}_films_with_values"] += bool(count)
        cast_with_character += metadata["cast_with_character_qualifier"]
        cast_without_character += metadata["cast_without_character_qualifier"]
        territory_dates += metadata["release_dates_with_territory"]
        referenced_dates += metadata["release_dates_with_references"]
        runtime_value_films += bool(metadata["value_statement_counts"]["runtime"])

    total_passages = sum(batch["passages"] for batch in batch_summaries)
    total_cited = sum(batch["citation_marker_passages"] for batch in batch_summaries)
    return {
        "schema": "cinegraph.english-catalog-pilot-capture-reconciliation/v1",
        "pilot_sha256": pilot_sha256,
        "expected_films": expected_count,
        "captured_films": len(selected),
        "exact_rank_title_year_qid_match": True,
        "all_sources_passed_integrity_audit": True,
        "batches": batch_summaries,
        "passages": total_passages,
        "passages_with_citation_markers": total_cited,
        "passage_citation_marker_coverage": round(total_cited / total_passages, 4) if total_passages else 0,
        "content_coverage": coverage,
        "wikidata_metadata": dict(sorted(totals.items())),
        "cast_credits_with_character_qualifier": cast_with_character,
        "cast_credits_without_character_qualifier": cast_without_character,
        "release_dates_with_territory": territory_dates,
        "release_dates_with_references": referenced_dates,
        "films_with_runtime_values": runtime_value_films,
        "content_gaps": [row for row in selected.values() if row["missing_content_categories"]],
        "films": [selected[rank] for rank in range(1, expected_count + 1)],
        "limitations": [
            "Verifies retained source identity, integrity and section availability, not semantic accuracy or rights approval.",
            "The first-ten capture originated from a different selection manifest; ranks were reconciled row by row and its distinct selection hash is retained.",
            "Wikidata counts are value-bearing source statements, not reviewed truth or proof of current API projection.",
            "Citation-marker presence does not prove source support or publication permission.",
            "No capture was ingested into the working database or embedding index.",
        ],
    }


def render_reconciliation_markdown(report: dict[str, Any]) -> str:
    """Render a text-free, human-readable summary of the reconciled capture."""
    coverage = report["content_coverage"]
    metadata = report["wikidata_metadata"]
    lines = [
        "# English 100-film source-capture reconciliation",
        "",
        f"Selection identity/integrity: **{'PASS' if report['all_sources_passed_integrity_audit'] and report['captured_films'] == report['expected_films'] else 'FAIL'}**",
        f"Exact pilot rows reconciled: **{report['captured_films']} / {report['expected_films']}**",
        f"Pilot manifest SHA-256: `{report['pilot_sha256']}`",
        f"Parsed source passages: {report['passages']:,}; citation-marker-bearing: {report['passages_with_citation_markers']:,} ({report['passage_citation_marker_coverage']:.1%})",
        "",
        "## Capture batches",
        "",
        "| Batch | Films | Selection hash matches frozen English pilot | Selection SHA-256 |",
        "| --- | ---: | --- | --- |",
    ]
    for batch in report["batches"]:
        lines.append(
            f"| {batch['label']} | {batch['requested']} | {'yes' if batch['selection_hash_matches_pilot'] else 'no; exact row reconciliation used'} | `{batch['selection_sha256']}` |"
        )
    lines.extend([
        "",
        "## Capture route policy fingerprints",
        "",
        "| Batch | Concurrency | Minimum interval | Wikidata robots SHA-256 | Wikipedia robots SHA-256 |",
        "| --- | ---: | ---: | --- | --- |",
    ])
    for batch in report["batches"]:
        policy = batch["capture_policy"] or {}
        lines.append(
            f"| {batch['label']} | {policy.get('concurrency', '—')} | {policy.get('minimum_interval_seconds', '—')} s | "
            f"`{batch['wikidata_robots_sha256'] or '—'}` | `{batch['wikipedia_robots_sha256'] or '—'}` |"
        )
    lines.extend([
        "",
        "## Source section availability",
        "",
        "| Category | Present | Missing |",
        "| --- | ---: | ---: |",
    ])
    for category, counts in coverage.items():
        lines.append(f"| {category.replace('_', ' ')} | {counts['films_with_section']} | {counts['films_missing_section']} |")
    lines.extend([
        "",
        "## Structured Wikidata coverage",
        "",
        "These are retained source-statement counts, not verified facts or current application projection coverage.",
        "",
        "| Property | Films with values | Value statements |",
        "| --- | ---: | ---: |",
    ])
    for key in sorted(metadata):
        if key.endswith("_films_with_values"):
            field = key.removesuffix("_films_with_values")
            lines.append(f"| {field.replace('_', ' ')} | {metadata[key]} | {metadata[f'{field}_statements']} |")
    lines.extend([
        "",
        f"Cast credits: {report['cast_credits_with_character_qualifier']:,} with explicit character qualifiers; {report['cast_credits_without_character_qualifier']:,} without.",
        f"Release-date statements with territory / references: {report['release_dates_with_territory']:,} / {report['release_dates_with_references']:,}.",
        f"Films with a runtime value: {report['films_with_runtime_values']} / {report['expected_films']}.",
        "",
        "## Content gaps",
        "",
    ])
    if report["content_gaps"]:
        for gap in report["content_gaps"]:
            lines.append(f"- Rank {gap['rank']}: {gap['title']} ({gap['year']}, `{gap['qid']}`) — {', '.join(gap['missing_content_categories'])}.")
    else:
        lines.append("- None for the audited plot and production categories.")
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend([
        "- Source snapshots, passages and per-film hashes are in the ignored local JSON reconciliation artifact, not this document.",
        "- Wikipedia text has not been approved for semantic indexing or redistribution; the source-rights review gate remains separate.",
    ])
    return "\n".join(lines) + "\n"
