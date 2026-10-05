"""Reconcile provisional film-profile language with reviewed Wikidata evidence.

The selection bucket is not a canonical original-language fact: P364 may have
several values. This job runs after Wikidata raw extraction and projection.
It never invents a language when there is no reviewed, raw-linked assertion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Assertion, AssertionEvidence, CanonicalEntity, DataSource, Film,
    SourceAssertion, SourceObject, SourceSnapshot,
)
from app.services.movie_data_gateway import _language, manifest_seeds
from app.services.research_metadata import language_code_for_qids


def reconcile_one(db: Session, wikidata_id: str, *, apply: bool,
                  approved_projected_language: str | None = None) -> dict:
    entity = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == wikidata_id))
    film = db.scalar(select(Film).where(Film.entity_id == entity.id)) if entity else None
    if film is None:
        return {"wikidata_id": wikidata_id, "status": "review_required", "reason": "no_film_profile"}
    rows = db.scalars(select(Assertion).join(
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
        Assertion.predicate == "original_language",
        Assertion.review_status.in_(("resolved", "published")),
        DataSource.name == "Wikidata",
        SourceObject.external_id == wikidata_id,
        SourceAssertion.source_property == "P364",
    )).unique()
    qids = {(row.value_json or {}).get("wikidata_id") for row in rows}
    qids.discard(None)
    if not qids:
        return {"wikidata_id": wikidata_id, "status": "review_required", "reason": "no_reviewed_language_source"}
    projected = language_code_for_qids(qids)
    result = {"wikidata_id": wikidata_id, "title": film.canonical_title,
              "source_language_qids": sorted(qids), "profile_language": film.original_language_code,
              "projected_language": projected}
    if film.original_language_code == projected:
        result["status"] = "already_consistent"
    elif film.review_status == "published" and approved_projected_language != projected:
        result.update(status="review_required", reason="published_profile_conflicts_with_source")
    elif apply:
        film.original_language_code = _language(db, projected)
        result["status"] = "updated"
    else:
        result["status"] = "ready"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Check profile languages against reviewed source values")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-updates", type=Path,
                        help="Operator-reviewed JSONL QID and expected language for published profiles")
    args = parser.parse_args()
    approved: dict[str, str] = {}
    if args.approved_updates:
        for line in args.approved_updates.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            qid, expected = row.get("wikidata_id"), row.get("expected_language_code")
            if not isinstance(qid, str) or not isinstance(expected, str) or not row.get("review_reason"):
                raise ValueError("Approved updates need QID, expected language and review reason")
            if qid in approved:
                raise ValueError(f"Duplicate reviewed QID: {qid}")
            approved[qid] = expected
    results = []
    with SessionLocal() as db:
        for seed in manifest_seeds(args.manifest):
            if not seed.wikidata_id:
                results.append({"title": seed.title, "status": "review_required",
                                "reason": "no_manifest_qid"})
                continue
            result = reconcile_one(db, seed.wikidata_id, apply=args.apply,
                                   approved_projected_language=approved.get(seed.wikidata_id))
            if args.apply:
                db.commit()
            results.append(result)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    print(json.dumps({"counts": counts, "report": str(args.report)}))


if __name__ == "__main__":
    main()
