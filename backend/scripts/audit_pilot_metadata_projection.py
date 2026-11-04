"""Read-only, per-film audit of profile dates/runtimes versus eligible evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import Assertion, CanonicalEntity, DataSource, Film
from app.services.pilot_metadata_audit import (
    classify_release_profile_date,
    classify_runtime_profile,
)
from app.services.research_catalog import research_films_from_entities


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--pilot", type=Path, default=Path("data/evaluation/catalog-pilot-top100-v5.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    local_evaluation = (Path.cwd() / "data/evaluation").resolve()
    if not args.pilot.resolve().is_relative_to(local_evaluation):
        raise ValueError("Pilot manifest must be under local data/evaluation")
    if not args.output.resolve().is_relative_to(local_evaluation) or args.output.exists():
        raise ValueError("Output must be a new file under local data/evaluation")
    pilot_bytes = args.pilot.read_bytes()
    pilot = json.loads(pilot_bytes)
    films = pilot.get("films")
    if pilot.get("film_count") != 100 or not isinstance(films, list) or len(films) != 100:
        raise ValueError("Expected the frozen 100-film pilot manifest")
    candidates = []
    for row in films:
        matches = row.get("catalog_candidates", [])
        if len(matches) != 1:
            raise ValueError(f"Pilot row {row.get('selection_rank')} lacks one catalog candidate")
        candidates.append({**row, "candidate": matches[0]})
    film_id_texts = [row["candidate"].get("film_id") for row in candidates]
    if any(not isinstance(film_id, str) for film_id in film_id_texts) or len(set(film_id_texts)) != 100:
        raise ValueError("Pilot candidate film IDs must be 100 unique strings")
    film_ids = [str(UUID(film_id)) for film_id in film_id_texts]

    url = make_url(args.database_url)
    if url.database != "cinegraph" or url.host not in {"db", "127.0.0.1", "localhost"}:
        raise ValueError("Audit is restricted to the local cinegraph database")
    engine = create_engine(args.database_url)
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            catalog_rows = db.execute(
                select(Film, CanonicalEntity)
                .join(CanonicalEntity, CanonicalEntity.id == Film.entity_id)
                .where(Film.id.in_(film_ids))
            ).all()
            profiles = {str(film.id): (film, entity) for film, entity in catalog_rows}
            if set(profiles) != set(film_ids):
                raise ValueError("One or more frozen pilot candidates are absent from the local catalog")
            entities = [profiles[film_id][1] for film_id in film_ids]
            research = research_films_from_entities(db, entities)
            research_by_entity = {item.entity_id: item for item in research}

            assertion_rows = db.execute(
                select(
                    Assertion.id,
                    Assertion.subject_entity_id,
                    Assertion.predicate,
                    Assertion.value_json,
                    Assertion.qualifiers,
                    Assertion.review_status,
                    Assertion.rank,
                    Assertion.source_reference,
                    Assertion.source_revision,
                    DataSource.name,
                    DataSource.url,
                    DataSource.rights_status,
                    DataSource.license,
                )
                .outerjoin(DataSource, DataSource.id == Assertion.source_id)
                .where(
                    Assertion.subject_entity_id.in_([entity.id for entity in entities]),
                    Assertion.predicate.in_(("release_event", "runtime")),
                    Assertion.assertion_kind == "source_fact",
                )
                .order_by(Assertion.subject_entity_id, Assertion.predicate, Assertion.id)
            ).all()
    finally:
        engine.dispose()

    assertions_by_entity: dict[object, list[dict]] = defaultdict(list)
    for row in assertion_rows:
        (assertion_id, entity_id, predicate, value, qualifiers, review_status, rank,
         source_reference, source_revision, source_name, source_url, rights_status, license_name) = row
        assertions_by_entity[entity_id].append({
            "assertion_id": str(assertion_id),
            "predicate": predicate,
            "value": value,
            "qualifiers": qualifiers,
            "review_status": review_status,
            "rank": rank,
            "source_reference": source_reference,
            "source_revision": source_revision,
            "source_name": source_name,
            "source_url": source_url,
            "source_rights_status": rights_status,
            "source_license": license_name,
        })

    results = []
    for row, film_id in zip(candidates, film_ids):
        film, entity = profiles[film_id]
        projection = research_by_entity[entity.id]
        assertions = assertions_by_entity[entity.id]
        runtime_assertions = [item for item in assertions if item["predicate"] == "runtime"]
        release_assertions = [item for item in assertions if item["predicate"] == "release_event"]
        runtime_rights = {item["source_rights_status"] for item in runtime_assertions}
        release_status = classify_release_profile_date(
            film.release_date,
            projection.release_events,
            projection.release_year,
            projection.release_date,
        )
        runtime_status = classify_runtime_profile(
            film.runtime_minutes,
            projection.runtime_minutes,
            projection.metadata_issues,
            runtime_rights,
        )
        results.append({
            "selection_rank": row["selection_rank"],
            "input_title": row["input_title"],
            "input_year": row["input_year"],
            "identity_state": row["match_status"],
            "film_id": film_id,
            "catalog_title": film.canonical_title,
            "wikidata_id": entity.wikidata_id,
            "legacy_profile": {
                "release_date": film.release_date.isoformat() if film.release_date else None,
                "runtime_minutes": film.runtime_minutes,
            },
            "default_display_research_projection": {
                "release_year": projection.release_year,
                "release_date": projection.release_date,
                "release_events": list(projection.release_events),
                "runtime_minutes": projection.runtime_minutes,
                "metadata_issues": list(projection.metadata_issues),
            },
            "release_profile_status": release_status,
            "runtime_profile_status": runtime_status,
            "source_assertions": {
                "release_events": [item for item in assertions if item["predicate"] == "release_event"],
                "runtimes": runtime_assertions,
            },
            "counts": {"release_assertions": len(release_assertions),
                       "runtime_assertions": len(runtime_assertions)},
        })

    report = {
        "version": "pilot-metadata-projection-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database_read_only": True,
        "pilot_sha256": hashlib.sha256(pilot_bytes).hexdigest(),
        "film_count": len(results),
        "release_profile_status_counts": dict(sorted(Counter(
            item["release_profile_status"] for item in results).items())),
        "runtime_profile_status_counts": dict(sorted(Counter(
            item["runtime_profile_status"] for item in results).items())),
        "films": results,
        "caution": "This compares local projections and recorded assertions; it does not establish factual accuracy, human review, or commercial reuse rights.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"film_count": report["film_count"],
                      "release_profile_status_counts": report["release_profile_status_counts"],
                      "runtime_profile_status_counts": report["runtime_profile_status_counts"],
                      "output": str(args.output), "database_read_only": True}))


if __name__ == "__main__":
    main()
