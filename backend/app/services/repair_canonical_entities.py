"""Repair incomplete canonical entity projections from retained Wikidata evidence.

This is deliberately narrow: it promotes only an ``unknown_work`` whose
retained Wikidata P31 statement explicitly says it is a film, and restores the
English label from the same raw statement subject. It never guesses from title
text or narrative prose.
"""
from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CanonicalEntity, SourceAssertion


FILM_QID = "Q11424"


def entity_id_from_statement(value: dict[str, Any]) -> str | None:
    return (
        value.get("datavalue", {})
        .get("value", {})
        .get("id")
        if isinstance(value, dict)
        else None
    )


def repair_unknown_films(db: Session) -> dict[str, int]:
    repaired = 0
    inspected = 0
    for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.entity_kind == "unknown_work")):
        inspected += 1
        statements = db.scalars(select(SourceAssertion).where(
            SourceAssertion.source_property == "P31",
            SourceAssertion.raw_subject["wikidata_id"].as_string() == entity.wikidata_id,
        ))
        for statement in statements:
            if entity_id_from_statement(statement.raw_value) != FILM_QID:
                continue
            label = str(statement.raw_subject.get("label") or "").strip()
            entity.entity_kind = "film"
            if label and entity.canonical_label == entity.wikidata_id:
                entity.canonical_label = label
            repaired += 1
            break
    db.flush()
    return {"inspected_unknown_work": inspected, "repaired_films": repaired}


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair unknown canonical works when retained Wikidata P31 proves film identity.")
    parser.add_argument("--apply", action="store_true", help="Persist repairs; omit for a dry-run report.")
    args = parser.parse_args()
    with SessionLocal() as db:
        result = repair_unknown_films(db)
        if args.apply:
            db.commit()
            print({**result, "mode": "applied"})
        else:
            db.rollback()
            print({**result, "mode": "dry-run"})


if __name__ == "__main__":
    main()
