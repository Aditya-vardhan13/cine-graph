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


def build_rows(pilot: dict[str, Any], readiness: dict[str, Any]) -> list[dict[str, Any]]:
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
    return rows


def render_markdown(rows: list[dict[str, Any]], *, pilot_sha256: str, readiness_sha256: str) -> str:
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
        "| # | CSV rank | Selected title | Catalog title | QID | Years | Runtime | D/W/C/Char | Narrative sections | Snapshots (total/attributed/approved/eligible) | Vectors (stored/eligible) | Gaps |",
        "|---:|---:|---|---|---|---|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        counts = row["resolved_assertions"]
        use = row["snapshots"]
        years = ", ".join(row["release_years"]) or "—"
        sections = ", ".join(row["sections"]) or "—"
        gaps = ", ".join(row["gaps"]) or "—"
        title = str(row["input_title"]).replace("|", "\\|")
        catalog_title = str(row["catalog_title"]).replace("|", "\\|")
        lines.append(
            f"| {row['rank']} | {row['input_rank']} | {title} ({row['input_year']}) | {catalog_title} | `{row['wikidata_id'] or '—'}` | {years} | {row['runtime_minutes'] or '—'} | "
            f"{counts['director']}/{counts['writer']}/{counts['cast']}/{counts['character']} | {sections} | "
            f"{use['total']}/{use['with_license_and_attribution']}/{use['approved']}/{use['eligible']} | "
            f"{row['vectors']['stored']}/{row['vectors']['eligible']} | {gaps} |"
        )
    lines.extend([
        "",
        "## Reproducibility",
        "",
        f"- English pilot manifest SHA-256: `{pilot_sha256}`",
        f"- Read-only catalog readiness SHA-256: `{readiness_sha256}`",
        "- Generated from local-only files under `data/evaluation/`; contains no passages and is not committed to Git.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-csv", type=Path, default=Path("imdb_top_1000.csv"))
    parser.add_argument("--pilot", type=Path, default=Path("data/evaluation/catalog-pilot-english100-v1.json"))
    parser.add_argument("--readiness", type=Path, default=Path("data/evaluation/catalog-readiness-v7.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/catalog-pilot-english100-coverage-v1.md"))
    args = parser.parse_args()
    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    if args.candidate_csv.resolve() != (project / "imdb_top_1000.csv").resolve():
        parser.error("Candidate CSV must be the supplied local imdb_top_1000.csv")
    if any(not path.resolve().is_relative_to(evaluation) for path in (args.pilot, args.readiness, args.output)):
        parser.error("Pilot inputs and output must remain under local data/evaluation")
    if args.output.exists():
        parser.error(f"Refusing to overwrite an existing versioned report: {args.output}")
    candidate_bytes = args.candidate_csv.read_bytes()
    pilot_bytes, readiness_bytes = args.pilot.read_bytes(), args.readiness.read_bytes()
    pilot, readiness = json.loads(pilot_bytes), json.loads(readiness_bytes)
    validate_english_catalog_pilot(pilot, candidate_bytes, readiness_bytes)
    rows = build_rows(pilot, readiness)
    document = render_markdown(rows, pilot_sha256=sha256(pilot_bytes), readiness_sha256=sha256(readiness_bytes))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(document)
    print(json.dumps({"films": len(rows), "output": str(args.output), "sha256": sha256(document.encode())}, indent=2))


if __name__ == "__main__":
    main()
