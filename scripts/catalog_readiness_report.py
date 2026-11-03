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
                credits = list(db.execute(select(FilmCredit.role, func.count(),
                    func.count(FilmCredit.character_name)).where(
                    FilmCredit.film_id == film.id,
                ).group_by(FilmCredit.role)))
                credit_counts = {role: {"count": count, "with_character": with_character}
                                 for role, count, with_character in credits}
                categories = set()
                source_versions = set()
                provenance = []
                for title, locator, revision, license_name, attribution, version in db.execute(
                    select(NarrativePassage.section_title, NarrativePassage.section_locator,
                           SourceSnapshot.source_revision, SourceSnapshot.license,
                           SourceSnapshot.attribution_url, NarrativePassage.extraction_version)
                    .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
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
                    provenance.append({"revision": revision, "license": license_name,
                                       "attributed": bool(attribution), "extraction_version": version})
                vector_count = db.scalar(select(func.count(EvidenceEmbedding.id)).join(
                    EvidenceChunk, EvidenceChunk.id == EvidenceEmbedding.evidence_chunk_id,
                ).where(EvidenceChunk.subject_entity_id == entity.id)) or 0
                result.append({
                    "film_id": str(film.id), "entity_id": str(entity.id),
                    "title": film.canonical_title, "wikidata_id": film.wikidata_id,
                    "aliases": [{"value": alias.value, "language": alias.language_code}
                                for alias in db.scalars(select(FilmAlias).where(FilmAlias.film_id == film.id))],
                    "language": film.original_language_code, "country_codes": film.country_codes,
                    "release_date": film.release_date.isoformat() if film.release_date else None,
                    "release_years_from_resolved_events": release_years,
                    "runtime_minutes": film.runtime_minutes,
                    "identity_status": "linked" if entity.wikidata_id == film.wikidata_id else "identity_conflict",
                    "resolved_assertions": dict(resolved), "credits_by_role": credit_counts,
                    "genres": db.scalar(select(func.count(FilmGenre.id)).where(FilmGenre.film_id == film.id)) or 0,
                    "narrative_categories": sorted(categories),
                    "source_versions": sorted(source_versions),
                    "source_snapshots": len(provenance),
                    "snapshots_with_license_and_attribution": sum(
                        bool(p["license"] and p["attributed"]) for p in provenance),
                    "embedding_vectors": vector_count,
                    "gaps": [field for field, value in {
                        "release_date": film.release_date,
                        "runtime_minutes": film.runtime_minutes,
                        "director": resolved["director"], "cast": resolved["cast"],
                        "character": resolved["character"], "plot": "plot" in categories,
                        "indexed": vector_count,
                    }.items() if not value],
                })
            report = {"version": "catalog-readiness-v1", "database_read_only": True,
                      "film_count": len(result), "films": result,
                      "caution": "Coverage indicators do not validate identity, factual correctness, rights eligibility, narrative relevance, or writer usefulness."}
    finally:
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"film_count": len(result), "output": str(args.output), "read_only": True}))


if __name__ == "__main__":
    main()
