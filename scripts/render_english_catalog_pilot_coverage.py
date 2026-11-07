"""Render a local-only field coverage sheet for the English 100-film pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.english_catalog_pilot import validate_english_catalog_pilot


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def add_cast_review_counts(
    rows: list[dict[str, Any]], report: dict[str, Any], *, pilot_sha256: str,
) -> None:
    """Attach unreviewed cast-candidate counts, never treating them as credits."""
    schema = report.get("schema")
    if schema not in {
        "cinegraph.wikipedia-cast-candidate-coverage/v1",
        "cinegraph.wikipedia-cast-candidate-coverage/v2",
    }:
        raise ValueError("Cast candidate report has an unsupported schema")
    if report.get("pilot_manifest_sha256") != pilot_sha256:
        raise ValueError("Cast candidate report is not bound to the exact English pilot manifest")
    summary = report.get("summary")
    if (not isinstance(summary, dict) or summary.get("films") != len(rows)
            or summary.get("all_candidates_review_required") is not True
            or summary.get("actor_character_credits_verified") is not False
            or summary.get("operational_assertions_written") is not False):
        raise ValueError("Cast candidate report must describe a full, review-only pilot audit")
    candidates = report.get("films")
    if not isinstance(candidates, list) or len(candidates) != len(rows):
        raise ValueError("Cast candidate report must cover every English pilot film")
    by_rank: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("selection_rank"), int):
            raise ValueError("Cast candidate rows must have an integer selection_rank")
        rank = candidate["selection_rank"]
        if rank in by_rank:
            raise ValueError(f"Cast candidate report repeats selection rank {rank}")
        by_rank[rank] = candidate
    expected = {row["rank"] for row in rows}
    if set(by_rank) != expected:
        raise ValueError("Cast candidate report rank set differs from the English pilot")

    fields = {
        "candidate_rows": "candidate_count",
        "same_film_identity_candidates": "same_film_identity_candidates",
        "identity_only_suggestions": "identity_only_suggestions",
        "unresolved_source_names": "unresolved_source_names",
        "quarantined_spans": "quarantined_spans",
        "review_only_drafts": "source_statement_drafts",
        "character_label_matches_only": "character_label_matches_only",
    }
    for row in rows:
        candidate = by_rank[row["rank"]]
        if candidate.get("film_qid") != row["wikidata_id"]:
            raise ValueError(f"Cast candidate Wikidata identity mismatch at pilot rank {row['rank']}")
        if candidate.get("title") != row["input_title"]:
            raise ValueError(f"Cast candidate title mismatch at pilot rank {row['rank']}")
        if candidate.get("year") != row["input_year"]:
            raise ValueError(f"Cast candidate release-year mismatch at pilot rank {row['rank']}")
        counts: dict[str, int] = {}
        for output_name, source_name in fields.items():
            value = candidate.get(source_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"Cast candidate count {source_name} is invalid at pilot rank {row['rank']}")
            counts[output_name] = value
        supplemented = candidate.get("identity_supplemented_candidates", 0)
        if (not isinstance(supplemented, int) or isinstance(supplemented, bool)
                or supplemented < 0 or supplemented > counts["identity_only_suggestions"]):
            raise ValueError(f"Supplemental identity count is invalid at pilot rank {row['rank']}")
        if schema.endswith("/v2") and "identity_supplemented_candidates" not in candidate:
            raise ValueError(f"Version-2 cast report lacks supplemental identity count at pilot rank {row['rank']}")
        quarantine_reasons = candidate.get("quarantine_reasons")
        if not isinstance(quarantine_reasons, dict) or any(
            not isinstance(reason, str) or not isinstance(count, int) or isinstance(count, bool) or count < 0
            for reason, count in quarantine_reasons.items()
        ):
            raise ValueError(f"Cast quarantine reasons are malformed at pilot rank {row['rank']}")
        if sum(quarantine_reasons.values()) != counts["quarantined_spans"]:
            raise ValueError(f"Cast quarantine totals disagree at pilot rank {row['rank']}")
        row["cast_review"] = {
            **counts,
            "identity_supplemented_candidates": supplemented,
            "quarantine_reasons": quarantine_reasons,
            "credit_status": "candidate_only_not_verified",
        }
    summary_to_rows = {
        "candidate_rows": "candidate_rows",
        "same_film_identity_candidates": "same_film_identity_candidates",
        "identity_only_suggestions": "identity_only_suggestions",
        "unresolved_source_names": "unresolved_source_names",
        "quarantined_spans": "quarantined_spans",
        "review_only_source_statement_drafts": "review_only_drafts",
        "character_label_matches_only": "character_label_matches_only",
    }
    for summary_name, row_name in summary_to_rows.items():
        if summary.get(summary_name) != sum(row["cast_review"][row_name] for row in rows):
            raise ValueError(f"Cast candidate summary {summary_name} does not match per-film rows")
    if schema.endswith("/v2"):
        supplemented = summary.get("identity_supplemented_candidates")
        if (not isinstance(supplemented, int) or isinstance(supplemented, bool)
                or supplemented != sum(row["cast_review"]["identity_supplemented_candidates"] for row in rows)):
            raise ValueError("Cast candidate supplemental identity summary does not match per-film rows")
    if summary.get("identity_only_candidates_with_review_drafts") != summary.get("identity_only_suggestions"):
        raise ValueError("Cast candidate identity-only draft count is inconsistent")


def build_rows(
    pilot: dict[str, Any], readiness: dict[str, Any],
    cast_review: dict[str, Any] | None = None, *, pilot_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """Join selected catalog IDs to one read-only readiness snapshot."""
    films = pilot.get("films")
    if pilot.get("film_count") != 100 or not isinstance(films, list) or len(films) != 100:
        raise ValueError("Expected the frozen English 100-film pilot")
    if readiness.get("database_read_only") is not True:
        raise ValueError("Readiness report must be marked database_read_only")
    readiness_films = readiness.get("films")
    if not isinstance(readiness_films, list):
        raise ValueError("Readiness report has no films list")
    by_id = {row.get("film_id"): row for row in readiness_films if isinstance(row, dict)}
    if len(by_id) != len(readiness_films) or any(not isinstance(key, str) for key in by_id):
        raise ValueError("Readiness report contains missing or duplicate film IDs")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in films:
        if not isinstance(item, dict):
            raise ValueError("Pilot contains a malformed film row")
        film_id = item.get("catalog_film_id")
        if not isinstance(film_id, str) or film_id in seen:
            raise ValueError("Pilot catalog film IDs must be unique strings")
        seen.add(film_id)
        if item.get("catalog_language") != "en":
            raise ValueError(f"Pilot row {item.get('selection_rank')} is not English-classified")
        ready = by_id.get(film_id)
        if ready is None:
            raise ValueError(f"Readiness report is missing pilot film {film_id}")
        if ready.get("wikidata_id") != item.get("wikidata_id"):
            raise ValueError(f"Wikidata identity mismatch for pilot row {item.get('selection_rank')}")
        if ready.get("language") != "en":
            raise ValueError(f"Readiness language mismatch for pilot row {item.get('selection_rank')}")
        use = ready.get("narrative_use_coverage")
        assertions = ready.get("resolved_assertions")
        if not isinstance(use, dict) or not isinstance(assertions, dict):
            raise ValueError(f"Readiness coverage fields are missing for pilot row {item.get('selection_rank')}")
        rows.append({
            "rank": item.get("selection_rank"),
            "input_rank": item.get("input_rank"),
            "input_title": item.get("input_title"),
            "input_year": item.get("input_year"),
            "catalog_title": ready.get("title"),
            "wikidata_id": ready.get("wikidata_id"),
            "identity_status": ready.get("identity_status"),
            "release_years": ready.get("release_years_from_resolved_events", []),
            "runtime_minutes": ready.get("runtime_minutes"),
            "resolved_assertions": {
                key: assertions.get(key, 0) for key in ("director", "writer", "cast", "character")
            },
            "sections": ready.get("narrative_categories", []),
            "source_versions": ready.get("source_versions", []),
            "snapshots": {
                key: use.get(key, 0) for key in (
                    "total", "with_license_and_attribution", "with_decision", "approved", "denied",
                    "review_required", "eligible",
                )
            },
            "vectors": {
                "stored": ready.get("embedding_vectors", 0),
                "eligible": ready.get("semantically_eligible_embedding_vectors", 0),
            },
            "gaps": ready.get("gaps", []),
        })
    if len(seen) != 100:
        raise ValueError("Coverage sheet does not contain 100 unique films")
    if cast_review is not None:
        if pilot_sha256 is None:
            raise ValueError("Exact pilot SHA-256 is required to join cast-candidate coverage")
        add_cast_review_counts(rows, cast_review, pilot_sha256=pilot_sha256)
    return rows


def render_markdown(
    rows: list[dict[str, Any]], *, pilot_sha256: str, readiness_sha256: str,
    cast_review_sha256: str | None = None,
) -> str:
    if len(rows) != 100:
        raise ValueError("Coverage sheet must contain exactly 100 rows")
    section_counts = {
        category: sum(category in row["sections"] for row in rows)
        for category in ("plot", "production", "reception", "themes", "legacy", "writing_craft")
    }
    totals = {
        key: sum(row["snapshots"][key] for row in rows)
        for key in ("total", "with_license_and_attribution", "approved", "eligible")
    }
    vector_totals = {key: sum(row["vectors"][key] for row in rows) for key in ("stored", "eligible")}
    has_cast_review = all("cast_review" in row for row in rows)
    lines = [
        "# English-first 100-film pilot — coverage sheet",
        "",
        "> Coverage is not verification of accuracy, completeness, rights clearance, or writer usefulness. Source passages are not included. `resolved` assertions are source-derived records, not necessarily human-reviewed facts.",
        "",
        "## Pilot summary",
        "",
        f"- Films: **{len(rows)}**, all selected from unique exact title/year catalog matches classified `en`.",
        "- Narrative section presence: " + ", ".join(f"{key} {value}/100" for key, value in section_counts.items()) + ".",
        f"- Narrative source snapshots: **{totals['total']}**; with license and attribution **{totals['with_license_and_attribution']}**; explicitly approved **{totals['approved']}**; eligible for semantic use **{totals['eligible']}**.",
        f"- Stored vectors: **{vector_totals['stored']}**; eligible under the current snapshot-purpose rights gate **{vector_totals['eligible']}**.",
        "- This readiness extract does not include the separate release/runtime snapshot-integrity audit or source text review. Empty or absent fields remain unknown; section presence is not a content-quality score.",
        "",
        "## Film-by-film readiness",
        "",
        "`D/W/C/Char` are resolved director/writer/cast/character assertion counts. Release years are sourced event years and may represent different territories; they are not silently collapsed to one date. `snapshots` shows total / attributed / approved / eligible narrative assets. `vectors` shows stored / rights-eligible derivatives. `gaps` come directly from the readiness report.",
        "",
    ]
    if has_cast_review:
        cast_totals = {
            key: sum(row["cast_review"][key] for row in rows)
            for key in ("candidate_rows", "same_film_identity_candidates", "identity_only_suggestions",
                        "unresolved_source_names", "quarantined_spans", "review_only_drafts",
                        "character_label_matches_only")
        }
        lines.extend([
            "- Wikipedia cast scan: **{candidate_rows} candidate rows**, **{same_film_identity_candidates} same-film identity candidates**, **{identity_only_suggestions} identity-only suggestions**, **{unresolved_source_names} unresolved names**, **{quarantined_spans} quarantined spans**, and **{review_only_drafts} review-only drafts**. These are not approved or verified actor–character credits.".format(**cast_totals),
            "- Character-label matches only: **{character_label_matches_only}**; label similarity is not actor–character evidence. Existing resolved cast/character assertions above are a separate catalog measure.".format(**cast_totals),
            "",
        ])
        if any("identity_supplemented_candidates" in row["cast_review"] for row in rows):
            supplemented_total = sum(
                row["cast_review"]["identity_supplemented_candidates"] for row in rows
            )
            lines.insert(
                len(lines) - 1,
                f"- Curated Wikidata identity supplement: **{supplemented_total}** additional source-name identities matched exact English labels/aliases; associated actor–character credits still require human review.",
            )
    lines.extend([
        ("| # | CSV rank | Selected title | Catalog title | QID | Years | Runtime | D/W/C/Char | Narrative sections | Snapshots (total/attributed/approved/eligible) | Vectors (stored/eligible) | Cast rows / review-only drafts / identity-only / unresolved / quarantined | Gaps |"
         if has_cast_review else
         "| # | CSV rank | Selected title | Catalog title | QID | Years | Runtime | D/W/C/Char | Narrative sections | Snapshots (total/attributed/approved/eligible) | Vectors (stored/eligible) | Gaps |"),
        ("|---:|---:|---|---|---|---|---:|---:|---|---:|---:|---:|---|"
         if has_cast_review else
         "|---:|---:|---|---|---|---|---:|---:|---|---:|---:|---|"),
    ])
    for row in rows:
        counts = row["resolved_assertions"]
        use = row["snapshots"]
        years = ", ".join(row["release_years"]) or "—"
        sections = ", ".join(row["sections"]) or "—"
        gaps = ", ".join(row["gaps"]) or "—"
        title = str(row["input_title"]).replace("|", "\\|")
        catalog_title = str(row["catalog_title"]).replace("|", "\\|")
        cast_cell = ""
        if has_cast_review:
            cast = row["cast_review"]
            cast_cell = (f"{cast['candidate_rows']} / {cast['review_only_drafts']} / "
                         f"{cast['identity_only_suggestions']} / "
                         f"{cast['unresolved_source_names']} / {cast['quarantined_spans']} | ")
        lines.append(
            f"| {row['rank']} | {row['input_rank']} | {title} ({row['input_year']}) | {catalog_title} | `{row['wikidata_id'] or '—'}` | {years} | {row['runtime_minutes'] or '—'} | "
            f"{counts['director']}/{counts['writer']}/{counts['cast']}/{counts['character']} | {sections} | "
            f"{use['total']}/{use['with_license_and_attribution']}/{use['approved']}/{use['eligible']} | "
            f"{row['vectors']['stored']}/{row['vectors']['eligible']} | {cast_cell}{gaps} |"
        )
    lines.extend([
        "",
        "## Reproducibility",
        "",
        f"- English pilot manifest SHA-256: `{pilot_sha256}`",
        f"- Read-only catalog readiness SHA-256: `{readiness_sha256}`",
        *([f"- Cast-candidate coverage SHA-256: `{cast_review_sha256}`",
           "- Cast-candidate counts are review leads only; this source audit contains no admin decision ledger or verified-credit count."]
          if cast_review_sha256 else []),
        "- Generated from local-only files under `data/evaluation/`; contains no passages and is not committed to Git.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-csv", type=Path, default=Path("imdb_top_1000.csv"))
    parser.add_argument("--pilot", type=Path, default=Path("data/evaluation/catalog-pilot-english100-v1.json"))
    parser.add_argument("--readiness", type=Path, default=Path("data/evaluation/catalog-readiness-v7.json"))
    parser.add_argument("--cast-candidate-coverage", type=Path,
                        help="Optional source-bound, review-only Wikipedia cast coverage JSON")
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/catalog-pilot-english100-coverage-v7.md"))
    args = parser.parse_args()
    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    if args.candidate_csv.resolve() != (project / "imdb_top_1000.csv").resolve():
        parser.error("Candidate CSV must be the supplied local imdb_top_1000.csv")
    scoped_paths = [args.pilot, args.readiness, args.output]
    if args.cast_candidate_coverage is not None:
        scoped_paths.append(args.cast_candidate_coverage)
    if any(not path.resolve().is_relative_to(evaluation) for path in scoped_paths):
        parser.error("Pilot inputs and output must remain under local data/evaluation")
    if args.output.exists():
        parser.error(f"Refusing to overwrite an existing versioned report: {args.output}")
    candidate_bytes = args.candidate_csv.read_bytes()
    pilot_bytes, readiness_bytes = args.pilot.read_bytes(), args.readiness.read_bytes()
    pilot, readiness = json.loads(pilot_bytes), json.loads(readiness_bytes)
    validate_english_catalog_pilot(pilot, candidate_bytes, readiness_bytes)
    cast_bytes = args.cast_candidate_coverage.read_bytes() if args.cast_candidate_coverage else None
    cast_review = json.loads(cast_bytes) if cast_bytes else None
    rows = build_rows(pilot, readiness, cast_review, pilot_sha256=sha256(pilot_bytes) if cast_review else None)
    document = render_markdown(
        rows, pilot_sha256=sha256(pilot_bytes), readiness_sha256=sha256(readiness_bytes),
        cast_review_sha256=sha256(cast_bytes) if cast_bytes else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(document)
    print(json.dumps({"films": len(rows), "output": str(args.output), "sha256": sha256(document.encode())}, indent=2))


if __name__ == "__main__":
    main()
