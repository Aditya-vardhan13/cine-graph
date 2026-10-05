"""Quarantine extra Wikidata IMDb IDs absent from the supplied local dump.

An extra P345 is retained as raw evidence, but must not remain a reviewed
operational identity when the selected IMDb ID is the only one present in the
operator's current IMDb title dataset. Existing alternative IDs are left for
manual review, never deleted or silently replaced.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Assertion, AssertionEvidence, CanonicalEntity, DataSource,
    SourceAssertion, SourceObject, SourceSnapshot,
)
from app.services.imdb_dataset import ImdbDataset
from app.services.movie_data_gateway import MovieSeed, manifest_seeds


def review_one(db: Session, dataset: ImdbDataset, seed: MovieSeed, *, apply: bool) -> dict:
    if not seed.imdb_id or not seed.wikidata_id:
        return {"title": seed.title, "status": "review_required", "reason": "manifest_ids_missing"}
    entity = db.scalar(select(CanonicalEntity).where(
        CanonicalEntity.wikidata_id == seed.wikidata_id,
    ))
    if entity is None:
        return {"title": seed.title, "status": "review_required", "reason": "canonical_qid_missing"}
    assertions = list(db.scalars(select(Assertion).join(
        DataSource, DataSource.id == Assertion.source_id,
    ).join(
        AssertionEvidence, AssertionEvidence.assertion_id == Assertion.id,
    ).join(
        SourceAssertion, SourceAssertion.id == AssertionEvidence.source_assertion_id,
    ).join(
        SourceSnapshot, SourceSnapshot.id == SourceAssertion.source_snapshot_id,
    ).join(
        SourceObject, SourceObject.id == SourceSnapshot.source_object_id,
    ).where(
        Assertion.subject_entity_id == entity.id,
        Assertion.predicate == "imdb_identifier",
        Assertion.review_status.in_(("resolved", "published")),
        DataSource.name == "Wikidata",
        SourceObject.external_id == seed.wikidata_id,
        SourceAssertion.source_property == "P345",
    )).unique())
    values = {(row.value_json or {}).get("value") for row in assertions}
    if seed.imdb_id not in values:
        return {"title": seed.title, "status": "review_required",
                "reason": "selected_imdb_id_not_in_reviewed_wikidata_p345",
                "wikidata_values": sorted(value for value in values if isinstance(value, str))}
    extras = [row for row in assertions if (row.value_json or {}).get("value") != seed.imdb_id]
    if not extras:
        return {"title": seed.title, "status": "unambiguous"}
    existing = [row for row in extras if dataset.rows("basics", (row.value_json or {}).get("value", ""))]
    if existing:
        return {"title": seed.title, "status": "review_required",
                "reason": "extra_imdb_id_exists_and_needs_manual_disambiguation",
                "extra_ids": sorted((row.value_json or {}).get("value") for row in existing)}
    if apply:
        for row in extras:
            row.review_status = "review_required"
    return {"title": seed.title, "status": "quarantined" if apply else "ready",
            "selected_imdb_id": seed.imdb_id,
            "extra_ids_absent_from_local_imdb": sorted((row.value_json or {}).get("value") for row in extras)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Review ambiguous Wikidata P345 film identities")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("/imports/imdb"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dataset = ImdbDataset(args.data_dir, args.index_dir)
    results = []
    with SessionLocal() as db:
        for seed in manifest_seeds(args.manifest):
            result = review_one(db, dataset, seed, apply=args.apply)
            if args.apply:
                db.commit()
            results.append(result)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(json.dumps({"counts": counts, "report": str(args.report)}))


if __name__ == "__main__":
    main()
