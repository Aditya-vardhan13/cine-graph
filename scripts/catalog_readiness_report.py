"""Read-only per-film catalog and narrative coverage report.

Writes no database rows. Output is a local audit artifact, not an approval of
identity, rights, source truth, or retrieval quality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import defaultdict
import re

from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import (
    Assertion, CanonicalEntity, EvidenceEmbedding, EvidenceChunk, Film, FilmAlias,
    FilmCredit, FilmGenre, NarrativePassage, SourceSnapshot,
)
from app.services.narrative_use_decisions import latest_decisions
from app.services.source_rights_policy import can_use_narrative_semantically


def _narrative_use_coverage(snapshots, decisions):
    """Summarize distinct source snapshots without treating missing decisions as approval."""
    counts = {"total": len(snapshots), "with_license_and_attribution": 0,
              "with_decision": 0, "approved": 0, "denied": 0, "review_required": 0,
              "eligible": 0}
    eligible_ids = set()
    for snapshot_id, license_name, attribution_url in snapshots:
        if license_name and attribution_url:
            counts["with_license_and_attribution"] += 1
        decision = decisions.get(snapshot_id)
        if decision is None:
            continue
        counts["with_decision"] += 1
        counts[decision.decision] += 1
        if (license_name == "CC BY-SA 4.0" and attribution_url
                and can_use_narrative_semantically(
                    decision=decision.decision,
                    basis_url=decision.decision_basis_url,
                    notes=decision.decision_notes,
                )):
            counts["eligible"] += 1
            eligible_ids.add(snapshot_id)
    return counts, eligible_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = make_url(args.database_url)
    if url.database != "cinegraph" or url.host not in {"db", "127.0.0.1", "localhost"}:
        raise ValueError("Readiness report is restricted to the local cinegraph database")
    root = Path("/workspace/data/evaluation").resolve()
    if not args.output.resolve().is_relative_to(root) or args.output.exists():
        raise ValueError("Output must be a new file inside local data/evaluation")
    engine = create_engine(args.database_url)
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            films = list(db.execute(select(Film, CanonicalEntity).join(
                CanonicalEntity, CanonicalEntity.id == Film.entity_id,
            ).order_by(Film.canonical_title, Film.id)))
            entity_ids = {entity.id for _film, entity in films}
            passage_snapshot_rows = list(db.execute(
                select(NarrativePassage.subject_entity_id, SourceSnapshot.id,
                       SourceSnapshot.source_revision, SourceSnapshot.license,
                       SourceSnapshot.attribution_url, NarrativePassage.extraction_version)
                .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
                .where(NarrativePassage.subject_entity_id.in_(entity_ids))
                .distinct()
            )) if entity_ids else []
            snapshots_by_entity = defaultdict(dict)
            for entity_id, snapshot_id, revision, license_name, attribution, version in passage_snapshot_rows:
                snapshots_by_entity[entity_id][snapshot_id] = {
                    "revision": revision, "license": license_name,
                    "attribution_url": attribution, "extraction_version": version,
                }
            all_snapshot_ids = {
                snapshot_id for snapshots in snapshots_by_entity.values()
                for snapshot_id in snapshots
            }
            decisions = latest_decisions(db, all_snapshot_ids)
            result = []
            for film, entity in films:
                resolved = defaultdict(int)
                release_events = []
                for pred, count in db.execute(select(Assertion.predicate, func.count()).where(
                    Assertion.subject_entity_id == entity.id,
                    Assertion.review_status == "resolved",
                ).group_by(Assertion.predicate)):
                    resolved[pred] = count
                release_events = list(db.scalars(select(Assertion.value_json).where(
                    Assertion.subject_entity_id == entity.id,
                    Assertion.predicate == "release_event",
                    Assertion.review_status == "resolved",
                )))
                release_years = sorted({match.group(1) for event in release_events
                    if isinstance(event, dict) and isinstance(event.get("time"), str)
                    for match in [re.match(r"^[+-]?(\d{4})", event["time"])] if match})
                imdb_ids = sorted({value.get("value") for value in db.scalars(select(Assertion.value_json).where(
                    Assertion.subject_entity_id == entity.id,
                    Assertion.predicate == "imdb_identifier",
                    Assertion.review_status == "resolved",
                )) if isinstance(value, dict) and isinstance(value.get("value"), str)})
                credits = list(db.execute(select(FilmCredit.role, func.count(),
                    func.count(FilmCredit.character_name)).where(
                    FilmCredit.film_id == film.id,
                ).group_by(FilmCredit.role)))
                credit_counts = {role: {"count": count, "with_character": with_character}
                                 for role, count, with_character in credits}
                categories = set()
                source_versions = set()
                for title, locator, version in db.execute(
                    select(NarrativePassage.section_title, NarrativePassage.section_locator,
                           NarrativePassage.extraction_version)
                    .where(NarrativePassage.subject_entity_id == entity.id)
                ):
                    heading = f"{title} {locator}".casefold()
                    for key, terms in {
                        "plot": ("plot", "synopsis", "story"),
                        "production": ("production", "development", "filming", "casting"),
                        "reception": ("reception", "critical response", "review", "accolade", "award"),
                        "themes": ("theme", "analysis", "interpretation"),
                        "legacy": ("legacy", "influence", "cultural impact"),
                        "writing_craft": ("screenplay", "writing", "cinematography", "editing", "music"),
                    }.items():
                        if any(term in heading for term in terms):
                            categories.add(key)
                    source_versions.add(version)
                film_snapshots = snapshots_by_entity.get(entity.id, {})
                use_coverage, eligible_snapshot_ids = _narrative_use_coverage(
                    [(snapshot_id, row["license"], row["attribution_url"])
                     for snapshot_id, row in film_snapshots.items()],
                    decisions,
                )
                vector_count = db.scalar(select(func.count(EvidenceEmbedding.id)).join(
                    EvidenceChunk, EvidenceChunk.id == EvidenceEmbedding.evidence_chunk_id,
                ).where(EvidenceChunk.subject_entity_id == entity.id)) or 0
                eligible_vector_count = db.scalar(select(func.count(EvidenceEmbedding.id)).join(
                    EvidenceChunk, EvidenceChunk.id == EvidenceEmbedding.evidence_chunk_id,
                ).where(
                    EvidenceChunk.subject_entity_id == entity.id,
                    EvidenceChunk.source_snapshot_id.in_(eligible_snapshot_ids),
                )) or 0
                result.append({
                    "film_id": str(film.id), "entity_id": str(entity.id),
                    "title": film.canonical_title, "wikidata_id": film.wikidata_id,
                    "aliases": [{"value": alias.value, "language": alias.language_code}
                                for alias in db.scalars(select(FilmAlias).where(FilmAlias.film_id == film.id))],
                    "resolved_imdb_ids": imdb_ids,
                    "language": film.original_language_code, "country_codes": film.country_codes,
                    "release_date": film.release_date.isoformat() if film.release_date else None,
                    "release_years_from_resolved_events": release_years,
                    "runtime_minutes": film.runtime_minutes,
                    "identity_status": "linked" if entity.wikidata_id == film.wikidata_id else "identity_conflict",
                    "resolved_assertions": dict(resolved), "credits_by_role": credit_counts,
                    "genres": db.scalar(select(func.count(FilmGenre.id)).where(FilmGenre.film_id == film.id)) or 0,
                    "narrative_categories": sorted(categories),
                    "source_versions": sorted(source_versions),
                    "source_snapshots": len(film_snapshots),
                    "narrative_use_coverage": use_coverage,
                    "embedding_vectors": vector_count,
                    "semantically_eligible_embedding_vectors": eligible_vector_count,
                    "gaps": [field for field, value in {
                        "release_date": film.release_date,
                        "runtime_minutes": film.runtime_minutes,
                        "director": resolved["director"], "cast": resolved["cast"],
                        "character": resolved["character"], "plot": "plot" in categories,
                        "indexed": vector_count,
                        "semantically_eligible_indexed": eligible_vector_count,
                    }.items() if not value],
                })
            report = {"version": "catalog-readiness-v2", "database_read_only": True,
                      "film_count": len(result), "films": result,
                      "caution": "Coverage indicators do not validate identity, factual correctness, commercial rights, narrative relevance, or writer usefulness. Semantic eligibility reports the latest recorded operator decision under the local policy, not legal advice."}
    finally:
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"film_count": len(result), "output": str(args.output), "read_only": True}))


if __name__ == "__main__":
    main()
