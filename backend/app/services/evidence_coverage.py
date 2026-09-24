"""Read-only, source-versioned passage coverage for the writer-study corpus.

Section headings are only an inventory proxy. They do not establish that a
film has a useful answer to any writer question, or that its source is sound.
Run snapshot-integrity and passage-equivalence audits separately.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CanonicalEntity, NarrativePassage, ReferenceCollectionMembership, SourceSnapshot


_SECTION_PATTERNS = {
    "plot": re.compile(r"\b(plot|synopsis|story)\b", re.I),
    "cast": re.compile(r"\b(cast|characters)\b", re.I),
    "production": re.compile(r"\b(production|development|filming|casting|post-production)\b", re.I),
    "writing_craft": re.compile(r"\b(writing|screenplay|script|cinematography|editing|music|score|visual effects)\b", re.I),
    "reception": re.compile(r"\b(reception|critical response|reviews?|accolades|awards)\b", re.I),
    "themes_analysis": re.compile(r"\b(themes?|analysis|interpretation)\b", re.I),
    "legacy": re.compile(r"\b(legacy|influence|cultural impact|retrospective)\b", re.I),
}


def section_categories(locator: str, title: str) -> tuple[str, ...]:
    """Classify headings, not passage meaning; a section can have many tags."""
    heading = f"{locator.replace('/', ' ')} {title}"
    return tuple(category for category, pattern in _SECTION_PATTERNS.items() if pattern.search(heading))


def passage_coverage_report(
    db: Session, *, collection_code: str, source_parser_version: str, include_films: bool = False,
) -> dict[str, object]:
    """Account for every included film and only one immutable-source version."""
    if not source_parser_version.strip():
        raise ValueError("source_parser_version is required for a provenance-scoped coverage report.")
    members = db.execute(
        select(ReferenceCollectionMembership.entity_id, CanonicalEntity.canonical_label)
        .join(CanonicalEntity, CanonicalEntity.id == ReferenceCollectionMembership.entity_id)
        .where(
            ReferenceCollectionMembership.collection_code == collection_code,
            ReferenceCollectionMembership.status == "included",
            CanonicalEntity.entity_kind == "film",
        )
        .order_by(ReferenceCollectionMembership.selection_position, CanonicalEntity.canonical_label)
    ).all()
    if not members:
        raise ValueError(f"No included films in collection {collection_code!r}.")
    film_rows: dict[object, dict[str, object]] = {
        entity_id: {"title": title, "passages": 0, "sections": set(), "categories": set()}
        for entity_id, title in members
    }
    rows = db.execute(
        select(
            NarrativePassage.subject_entity_id, NarrativePassage.section_locator,
            NarrativePassage.section_title,
        )
        .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
        .where(
            NarrativePassage.subject_entity_id.in_(film_rows),
            SourceSnapshot.parser_version == source_parser_version,
        )
    )
    for entity_id, locator, title in rows:
        film = film_rows[entity_id]
        film["passages"] += 1
        film["sections"].add(locator)
        film["categories"].update(section_categories(locator, title))
    category_counts = Counter(category for film in film_rows.values() for category in film["categories"])
    missing = [film["title"] for film in film_rows.values() if film["passages"] == 0]
    report: dict[str, object] = {
        "collection_code": collection_code,
        "source_parser_version": source_parser_version,
        "basis": "section-heading inventory; not verified content quality or snapshot integrity",
        "films": len(film_rows),
        "films_with_passages": len(film_rows) - len(missing),
        "films_without_passages": len(missing),
        "passages": sum(film["passages"] for film in film_rows.values()),
        "films_with_category": {key: category_counts[key] for key in _SECTION_PATTERNS},
        "missing_examples": missing[:20],
    }
    if include_films:
        report["film_rows"] = [
            {
                "entity_id": str(entity_id), "title": film["title"],
                "passages": film["passages"], "section_count": len(film["sections"]),
                "categories": sorted(film["categories"]),
            }
            for entity_id, film in film_rows.items()
        ]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only, per-film narrative coverage audit for one source version.")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--source-parser-version", required=True)
    parser.add_argument("--include-films", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        report = passage_coverage_report(
            db, collection_code=args.collection, source_parser_version=args.source_parser_version,
            include_films=args.include_films,
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
