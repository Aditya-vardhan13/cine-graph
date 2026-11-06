"""Render a human-readable, local-only coverage sheet for the frozen 100-film pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _film_index(document: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    films = document.get("films")
    if not isinstance(films, list):
        raise ValueError(f"{key} report has no films list")
    rows = {row.get("film_id"): row for row in films if isinstance(row, dict)}
    if len(rows) != len(films) or any(not isinstance(film_id, str) for film_id in rows):
        raise ValueError(f"{key} report has missing or duplicate film IDs")
    return rows


def build_coverage_rows(
    pilot: dict[str, Any], readiness: dict[str, Any], metadata: dict[str, Any], *, pilot_sha256: str,
    identity_decisions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Join only reports tied to the same frozen film IDs; never infer missing values."""
    pilot_films = pilot.get("films")
    if pilot.get("film_count") != 100 or not isinstance(pilot_films, list) or len(pilot_films) != 100:
        raise ValueError("Expected the frozen 100-film pilot")
    if readiness.get("database_read_only") is not True:
        raise ValueError("Readiness report must be marked database_read_only")
    if metadata.get("database_read_only") is not True or metadata.get("pilot_sha256") != pilot_sha256:
        raise ValueError("Metadata report is not a read-only audit of these exact pilot bytes")
    pilot_crosslink_ranks = {
        item.get("selection_rank") for item in pilot_films
        if isinstance(item, dict) and item.get("match_status") == "review_required_unique_imdb_crosslink"
    }
    decisions_by_rank: dict[int, dict[str, Any]] = {}
    if identity_decisions is not None:
        if identity_decisions.get("input_sha256", {}).get("pilot") != pilot_sha256:
            raise ValueError("Identity decisions are not bound to these exact pilot bytes")
        if identity_decisions.get("scope") != "pilot membership only; no catalog identity merge and no IMDb field reuse":
            raise ValueError("Identity decision scope is broader than pilot membership")
        decisions = identity_decisions.get("decisions")
        if not isinstance(decisions, list) or identity_decisions.get("decision_count") != len(decisions):
            raise ValueError("Identity decision count does not match its decisions")
        for decision in decisions:
            rank = decision.get("selection_rank") if isinstance(decision, dict) else None
            if type(rank) is not int or rank in decisions_by_rank:
                raise ValueError("Identity decisions must have unique integer selection ranks")
            if (decision.get("decision") != "accepted_same_work_for_pilot_membership_only"
                    or decision.get("operational_identity_merged") is not False
                    or decision.get("source_fields_authorized_for_product") is not False):
                raise ValueError("Identity decision must remain selection-only and non-authorizing")
            decisions_by_rank[rank] = decision
        if set(decisions_by_rank) != pilot_crosslink_ranks:
            raise ValueError("Identity decisions must cover exactly the pilot crosslink rows")
    readiness_by_id = _film_index(readiness, "readiness")
    metadata_by_id = _film_index(metadata, "metadata")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in pilot_films:
        candidates = item.get("catalog_candidates") or []
        if len(candidates) != 1:
            raise ValueError(f"Pilot row {item.get('selection_rank')} must have one selected candidate")
        candidate = candidates[0]
        film_id = candidate.get("film_id")
        if not isinstance(film_id, str) or film_id in seen:
            raise ValueError("Pilot candidate film IDs must be unique strings")
        seen.add(film_id)
        ready = readiness_by_id.get(film_id)
        meta = metadata_by_id.get(film_id)
        if ready is None or meta is None:
            raise ValueError(f"Current audit is missing pilot candidate {film_id}")
        if ready.get("wikidata_id") != candidate.get("wikidata_id") or meta.get("wikidata_id") != candidate.get("wikidata_id"):
            raise ValueError(f"Source identity mismatch for pilot rank {item.get('selection_rank')}")
        rank = item["selection_rank"]
        decision = decisions_by_rank.get(rank)
        match_status = item["match_status"]
        if match_status == "review_required_unique_imdb_crosslink":
            if decision is None:
                identity_label = "crosslink: review required"
            else:
                if (decision.get("film_id") != film_id
                        or decision.get("wikidata_id") != candidate.get("wikidata_id")
                        or decision.get("input_title") != item.get("input_title")
                        or decision.get("input_year") != item.get("input_year")):
                    raise ValueError(f"Identity decision does not match pilot rank {rank}")
                identity_label = "crosslink: pilot membership only"
        else:
            if decision is not None:
                raise ValueError(f"Unexpected identity decision for non-crosslink pilot rank {rank}")
            identity_label = match_status.replace("_", " ")
        projection = meta["default_display_research_projection"]
        use = ready["narrative_use_coverage"]
        assertions = ready["resolved_assertions"]
        runtime_options = projection["runtime_options"]
        rows.append({
            "rank": item["selection_rank"],
            "title": item["input_title"],
            "input_year": item["input_year"],
            "catalog_title": ready["title"],
            "language": ready.get("language") or "unknown",
            "identity": identity_label,
            "sections": ready["narrative_categories"],
            "assertions": {name: int(assertions.get(name, 0)) for name in ("director", "cast", "character")},
            "release": {
                "status": meta["release_profile_status"],
                "legacy_date": meta["legacy_profile"].get("release_date"),
                "research_date": projection.get("release_date"),
                "research_year": projection.get("release_year"),
            },
            "runtime": {
                "status": meta["runtime_profile_status"],
                "legacy_minutes": meta["legacy_profile"].get("runtime_minutes"),
                "options": [option.get("minutes") for option in runtime_options],
                "option_count": len(runtime_options),
            },
            "narrative": {
                "snapshots": use["total"],
                "with_license_attribution": use["with_license_and_attribution"],
                "approved": use["approved"],
                "eligible": use["eligible"],
            },
            "vectors": {
                "stored": ready["embedding_vectors"],
                "eligible": ready["semantically_eligible_embedding_vectors"],
            },
        })
    if len(seen) != 100:
        raise ValueError("Coverage sheet does not contain 100 unique films")
    return rows


def render_markdown(
    rows: list[dict[str, Any]], readiness: dict[str, Any], metadata: dict[str, Any],
    *, pilot_sha256: str, readiness_sha256: str, metadata_sha256: str,
    identity_decisions_sha256: str | None = None,
) -> str:
    """Render summary plus a compact per-film decision queue."""
    if len(rows) != 100:
        raise ValueError("Coverage sheet must contain exactly 100 rows")
    narrative_totals = {
        key: sum(row["narrative"][key] for row in rows)
        for key in ("snapshots", "with_license_attribution", "approved", "eligible")
    }
    vector_totals = {key: sum(row["vectors"][key] for row in rows) for key in ("stored", "eligible")}
    section_counts = {
        key: sum(key in row["sections"] for row in rows)
        for key in ("plot", "production", "reception", "themes", "legacy", "writing_craft")
    }
    identity_counts: dict[str, int] = {}
    for row in rows:
        identity_counts[row["identity"]] = identity_counts.get(row["identity"], 0) + 1
    language_counts: dict[str, int] = {}
    for row in rows:
        language = row["language"]
        language_counts[language] = language_counts.get(language, 0) + 1

    integrity_counts = metadata["snapshot_integrity"]["unique_snapshot_status_counts"]
    integrity_summary = ", ".join(
        f"{status} {count}" for status, count in sorted(integrity_counts.items())
    ) or "no snapshot records"

    lines = [
        "# Frozen 100-film pilot — coverage sheet",
        "",
        f"Audit generated: `{metadata.get('generated_at', 'timestamp unavailable')}` (UTC)",
        "",
        "> Coverage only. A section heading or resolved assertion is not proof of correctness, depth, rights clearance, or writer usefulness. Narrative text remains excluded from model use until its exact snapshot has an explicit eligible decision.",
        "",
        "## Snapshot",
        "",
        f"- Films: **{len(rows)}**; identity states: " + ", ".join(f"`{key}` {value}" for key, value in sorted(identity_counts.items())) + ".",
        "- Catalog original-language codes: " + ", ".join(f"`{key}` {value}" for key, value in sorted(language_counts.items())) + ". `und` is unclassified, not English; `mul` is multilingual.",
        "- Section presence: " + ", ".join(f"{key} {section_counts[key]}/100" for key in section_counts) + ".",
        f"- Narrative snapshots: **{narrative_totals['snapshots']}**; with license and attribution **{narrative_totals['with_license_attribution']}**; approved **{narrative_totals['approved']}**; semantically eligible **{narrative_totals['eligible']}**.",
        f"- Stored vectors: **{vector_totals['stored']}**; vectors eligible under current rights policy: **{vector_totals['eligible']}**.",
        f"- Snapshot integrity (release/runtime evidence only): {integrity_summary}; unlinked evidence references: {metadata['snapshot_integrity']['evidence_references_without_snapshot']}.",
        "- A crosslink accepted for pilot membership is not a catalog identity merge and does not authorize reuse of IMDb fields. Unadjudicated crosslinks remain marked for review.",
        "",
        "## Film-by-film review queue",
        "",
        "The identity column distinguishes exact title/year matches from crosslinks accepted for pilot-list membership only. Where names differ, both the selected-list title and catalog title are shown. `sections` means a passage is classified under a matching article heading; it does not score passage quality. Credit figures are resolved source assertions, not distinct people or verified character completeness. Runtime options preserve source/version alternatives.",
        "",
        "| # | Selected title | Lang. | Identity | Sections present | Resolved assertions (D/C/Char) | Release: legacy → research | Runtime status (options, min) | Narrative snapshots (eligible) | Vectors (eligible) |",
        "|---:|---|---|---|---|---:|---|---|---:|---:|",
    ]
    for row in rows:
        sections = ", ".join(row["sections"]) or "—"
        assertions = row["assertions"]
        release = row["release"]
        legacy_date = release["legacy_date"] or "—"
        sourced_date = release["research_date"] or (str(release["research_year"]) if release["research_year"] else "—")
        runtime = row["runtime"]
        runtime_values = ", ".join(str(value) for value in runtime["options"]) or "—"
        options = f"{runtime['option_count']}: {runtime_values}"
        narrative = row["narrative"]
        vectors = row["vectors"]
        selected_title = f"{row['title']} ({row['input_year']})"
        catalog_title = row["catalog_title"]
        title = selected_title if row["title"].casefold() == catalog_title.casefold() else f"{selected_title} → {catalog_title}"
        title = title.replace("|", "\\|")
        lines.append(
            f"| {row['rank']} | {title} | {row['language']} | `{row['identity']}` "
            f"| {sections} | {assertions['director']}/{assertions['cast']}/{assertions['character']} "
            f"| `{release['status']}`: {legacy_date} → {sourced_date} "
            f"| `{runtime['status']}` ({options}) "
            f"| {narrative['snapshots']} ({narrative['eligible']}) "
            f"| {vectors['stored']} ({vectors['eligible']}) |"
        )
    lines.extend([
        "",
        "## Reproducibility",
        "",
        f"- Pilot manifest SHA-256: `{pilot_sha256}`",
        f"- Current read-only readiness report SHA-256: `{readiness_sha256}`",
        f"- Current read-only metadata report SHA-256: `{metadata_sha256}`",
        f"- Pilot identity-decision sidecar SHA-256: `{identity_decisions_sha256 or 'not supplied'}`",
        "- This report is generated from local-only files under `data/evaluation/`; it contains no source passages and is not committed to Git.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=Path("data/evaluation/catalog-pilot-top100-v5.json"))
    parser.add_argument("--readiness", type=Path, default=Path("data/evaluation/catalog-readiness-v7.json"))
    parser.add_argument("--metadata", type=Path, default=Path("data/evaluation/catalog-pilot-metadata-audit-v11.json"))
    parser.add_argument("--identity-decisions", type=Path, default=Path("data/evaluation/catalog-pilot-identity-decisions-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/catalog-pilot-coverage-v4.md"))
    args = parser.parse_args()
    evaluation = (Path.cwd() / "data/evaluation").resolve()
    inputs = (args.pilot, args.readiness, args.metadata, args.identity_decisions)
    if any(not path.resolve().is_relative_to(evaluation) for path in (*inputs, args.output)):
        parser.error("Pilot inputs and output must remain under local data/evaluation")
    if args.output.exists():
        parser.error(f"Refusing to overwrite an existing versioned report: {args.output}")
    payloads = [path.read_bytes() for path in inputs]
    pilot, readiness, metadata, identity_decisions = [json.loads(payload) for payload in payloads]
    rows = build_coverage_rows(
        pilot, readiness, metadata, pilot_sha256=_sha256(payloads[0]),
        identity_decisions=identity_decisions,
    )
    document = render_markdown(
        rows, readiness, metadata,
        pilot_sha256=_sha256(payloads[0]),
        readiness_sha256=_sha256(payloads[1]),
        metadata_sha256=_sha256(payloads[2]),
        identity_decisions_sha256=_sha256(payloads[3]),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    print(json.dumps({"films": len(rows), "output": str(args.output), "sha256": _sha256(document.encode())}))


if __name__ == "__main__":
    main()
