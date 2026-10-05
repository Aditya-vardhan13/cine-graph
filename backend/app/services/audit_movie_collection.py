"""Read-only evidence/coverage audit for a film research collection."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Assertion, CanonicalEntity, DataSource, EntityResolution, Film, NarrativePassage,
    ReferenceCollectionMembership, SourceObject, SourceSnapshot,
)


def section_coverage(sections: set[str]) -> dict[str, bool]:
    """Recognize ordinary article headings without treating a lead as a plot."""
    roots = {section.split("/", 1)[0].strip().casefold() for section in sections}
    return {
        "plot": bool(roots & {"plot", "plot-summary", "synopsis", "premise", "story", "storyline"}),
        "production": any("production" in section for section in sections),
        "reception": any(term in section for section in sections
                         for term in ("reception", "review", "critical-response")),
        "legacy": any(term in section for section in sections
                      for term in ("legacy", "impact", "influence")),
    }


def audit_collection(db: Session, code: str) -> dict:
    members = list(db.scalars(select(ReferenceCollectionMembership).where(
        ReferenceCollectionMembership.collection_code == code,
        ReferenceCollectionMembership.status == "included",
    )))
    ids = {member.entity_id for member in members}
    if not ids:
        raise ValueError(f"Collection {code} has no included films")
    entities = {row.id: row for row in db.scalars(select(CanonicalEntity).where(
        CanonicalEntity.id.in_(ids),
    ))}
    profiles = {row.entity_id: row for row in db.scalars(select(Film).where(
        Film.entity_id.in_(ids),
    ))}
    sources = {row.id: row.name for row in db.scalars(select(DataSource))}
    facts: dict[UUID, list[Assertion]] = defaultdict(list)
    for row in db.scalars(select(Assertion).where(
        Assertion.subject_entity_id.in_(ids),
        Assertion.review_status.in_(("resolved", "published")),
    )):
        facts[row.subject_entity_id].append(row)
    passages: dict[UUID, list[NarrativePassage]] = defaultdict(list)
    for row in db.scalars(select(NarrativePassage).where(
        NarrativePassage.subject_entity_id.in_(ids),
    )):
        passages[row.subject_entity_id].append(row)
    imdb_objects = set(db.scalars(select(SourceObject.external_id).join(
        DataSource, DataSource.id == SourceObject.source_id,
    ).join(SourceSnapshot, SourceSnapshot.source_object_id == SourceObject.id).where(
        DataSource.name == "IMDb Non-Commercial Datasets",
        SourceSnapshot.fetch_status == "success",
    )))
    wikidata_objects = set(db.scalars(select(SourceObject.external_id).join(
        DataSource, DataSource.id == SourceObject.source_id,
    ).join(SourceSnapshot, SourceSnapshot.source_object_id == SourceObject.id).where(
        DataSource.name == "Wikidata",
        SourceSnapshot.fetch_status == "success",
    )))
    tmdb_entities = set(db.scalars(select(EntityResolution.entity_id).join(
        SourceObject, SourceObject.id == EntityResolution.source_object_id,
    ).join(
        DataSource, DataSource.id == SourceObject.source_id,
    ).join(
        SourceSnapshot, SourceSnapshot.id == EntityResolution.source_snapshot_id,
    ).where(
        EntityResolution.entity_id.in_(ids),
        EntityResolution.status == "resolved",
        DataSource.name == "TMDb Developer API",
        SourceSnapshot.fetch_status == "success",
    )))
    counts: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    gaps: list[dict] = []
    identity_failures: list[dict] = []
    sampled: list[dict] = []
    for entity_id in sorted(ids, key=lambda value: entities[value].canonical_label):
        entity = entities[entity_id]
        profile = profiles.get(entity_id)
        active = facts[entity_id]
        imdb_ids = {(row.value_json or {}).get("value") for row in active
                    if row.predicate == "imdb_identifier" and
                    sources.get(row.source_id) == "IMDb Non-Commercial Datasets"}
        imdb_ids.discard(None)
        imdb_id = next(iter(imdb_ids)) if len(imdb_ids) == 1 else None
        wikidata_imdb_ids = {(row.value_json or {}).get("value") for row in active
                              if row.predicate == "imdb_identifier" and
                              sources.get(row.source_id) == "Wikidata"}
        wikidata_imdb_ids.discard(None)
        tmdb_imdb_ids = {(row.value_json or {}).get("value") for row in active
                           if row.predicate == "imdb_identifier" and
                           sources.get(row.source_id) == "TMDb Developer API"}
        tmdb_imdb_ids.discard(None)
        source_cast = [row for row in active if row.predicate == "cast" and
                       sources.get(row.source_id) == "IMDb Non-Commercial Datasets"]
        tmdb_cast = [row for row in active if row.predicate == "cast" and
                     sources.get(row.source_id) == "TMDb Developer API"]
        character_count = sum(bool((row.value_json or {}).get("characters")) for row in source_cast)
        tmdb_character_count = sum(bool((row.value_json or {}).get("character")) for row in tmdb_cast)
        wiki_sections = {row.section_locator.replace(" / ", "/").casefold()
                         for row in passages[entity_id]}
        axes = section_coverage(wiki_sections)
        issues = []
        if not profile:
            issues.append("no_film_profile")
        else:
            counts["film_profiles"] += 1
            languages[profile.original_language_code] += 1
        if not imdb_id or imdb_id not in imdb_objects:
            issues.append("no_verified_imdb_snapshot")
        else:
            counts["verified_imdb_snapshot"] += 1
        if entity.wikidata_id not in wikidata_objects:
            issues.append("no_wikidata_snapshot")
        else:
            counts["wikidata_snapshot"] += 1
        if imdb_id and wikidata_imdb_ids == {imdb_id}:
            counts["wikidata_imdb_identity_agrees"] += 1
        else:
            issues.append("wikidata_imdb_identity_unproved_or_conflicting")
            identity_failures.append({"title": entity.canonical_label,
                                      "imdb_id": imdb_id,
                                      "wikidata_imdb_ids": sorted(wikidata_imdb_ids)})
        if entity_id in tmdb_entities:
            counts["tmdb_snapshot"] += 1
            if imdb_id and tmdb_imdb_ids == {imdb_id}:
                counts["tmdb_imdb_identity_agrees"] += 1
            else:
                issues.append("tmdb_imdb_identity_unproved_or_conflicting")
                identity_failures.append({"title": entity.canonical_label,
                                          "imdb_id": imdb_id,
                                          "tmdb_imdb_ids": sorted(tmdb_imdb_ids)})
        if tmdb_cast:
            counts["with_tmdb_cast"] += 1
        if tmdb_character_count:
            counts["with_tmdb_character"] += 1
        if any(row.section_locator == "tmdb.overview" for row in passages[entity_id]):
            counts["with_tmdb_overview"] += 1
        if source_cast:
            counts["with_imdb_cast"] += 1
        else:
            issues.append("no_imdb_cast")
        if character_count:
            counts["with_imdb_character"] += 1
        else:
            issues.append("no_imdb_character")
        if character_count or tmdb_character_count:
            counts["with_any_character_credit"] += 1
        else:
            issues.append("no_character_credit")
        if passages[entity_id]:
            counts["with_narrative_passages"] += 1
        else:
            issues.append("no_narrative_passages")
        if axes["plot"]:
            counts["with_plot_passage"] += 1
        else:
            issues.append("no_plot_passage")
        if axes["production"]:
            counts["with_production_passage"] += 1
        if axes["reception"]:
            counts["with_reception_passage"] += 1
        if axes["legacy"]:
            counts["with_legacy_or_impact_passage"] += 1
        if any(row.predicate == "release_event" and
               sources.get(row.source_id) == "Wikidata" and
               (row.value_json or {}).get("precision", 0) >= 11
               for row in active):
            counts["with_wikidata_day_release"] += 1
        if any(row.predicate == "release_event" and
               sources.get(row.source_id) == "TMDb Developer API" and
               (row.value_json or {}).get("precision") == "day"
               for row in active):
            counts["with_tmdb_day_release"] += 1
        if issues:
            gaps.append({"title": entity.canonical_label, "wikidata_id": entity.wikidata_id,
                         "imdb_id": imdb_id, "issues": issues,
                         "source_sections": sorted(wiki_sections)[:20]})
        if len(sampled) < 12 and passages[entity_id]:
            sampled.append({"title": entity.canonical_label,
                            "sections": sorted(wiki_sections)[:12],
                            "passages": len(passages[entity_id]),
                            "imdb_cast": len(source_cast),
                            "imdb_character_credits": character_count})
    return {"collection": code, "films": len(ids), "coverage": dict(sorted(counts.items())),
            "profile_languages": dict(sorted(languages.items())),
            "gap_films": len(gaps), "gaps": gaps,
            "identity_failure_count": len(identity_failures),
            "identity_failures": identity_failures, "sample": sampled,
            "interpretation": "Counts measure source-backed coverage, not independent correctness or artistic quality."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a local source-backed film collection")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        report = audit_collection(db, args.collection)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"films": report["films"], "coverage": report["coverage"],
                      "gap_films": report["gap_films"], "report": str(args.report)}))


if __name__ == "__main__":
    main()
