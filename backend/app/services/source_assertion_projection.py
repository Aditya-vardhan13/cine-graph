"""Project current immutable source statements into the operational Assertion graph.

The projector is deliberately separate from acquisition. It reads only the
latest retained successful snapshot for each Wikidata object, is safe to
resume, and records a direct foreign-key evidence path back to every raw
statement it publishes.
"""
from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Assertion,
    AssertionEvidence,
    CanonicalEntity,
    DataSource,
    EntityResolution,
    ReferenceCollectionMembership,
    SourceAssertion,
    SourceObject,
    SourceSnapshot,
)
from app.services.source_assertion_policy import (
    SOURCE_PROPERTY_RULES,
    ProjectionDecision,
    project_wikidata_statement,
    review_status_for_target,
)


PROJECTOR_VERSION = "wikidata-source-assertion-projector-v1"
WIKIDATA_SOURCE_NAME = "Wikidata"


def _latest_snapshot_subquery():
    ranked = select(
        SourceSnapshot.id.label("snapshot_id"),
        SourceSnapshot.source_object_id.label("source_object_id"),
        func.row_number().over(
            partition_by=SourceSnapshot.source_object_id,
            order_by=(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc()),
        ).label("snapshot_rank"),
    ).where(SourceSnapshot.fetch_status == "success").subquery()
    return select(
        ranked.c.snapshot_id, ranked.c.source_object_id,
    ).where(ranked.c.snapshot_rank == 1).subquery()


def _source_reference(snapshot: SourceSnapshot, assertion: SourceAssertion) -> str:
    reference = f"{snapshot.canonical_url}#{assertion.statement_locator}"
    if len(reference) > 500:
        raise ValueError(f"Source assertion reference exceeds 500 characters: {assertion.id}")
    return reference


def _ensure_targets(
    db: Session,
    decisions: dict[UUID, ProjectionDecision],
) -> tuple[dict[str, CanonicalEntity], int]:
    qids = {decision.object_qid for decision in decisions.values() if decision.object_qid}
    targets = {
        entity.wikidata_id: entity
        for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.in_(qids)))
        if entity.wikidata_id
    } if qids else {}
    created = 0
    for decision in decisions.values():
        qid = decision.object_qid
        if not qid or qid in targets:
            continue
        target = CanonicalEntity(
            entity_kind=decision.object_kind or "unknown_work",
            canonical_label=qid,
            wikidata_id=qid,
        )
        db.add(target)
        targets[qid] = target
        created += 1
    if created:
        db.flush()
    return targets, created


def _retract_superseded(
    db: Session,
    latest,
    collection_code: str | None,
) -> int:
    statement = select(Assertion).join(
        AssertionEvidence, AssertionEvidence.assertion_id == Assertion.id,
    ).join(
        SourceAssertion, SourceAssertion.id == AssertionEvidence.source_assertion_id,
    ).join(
        SourceSnapshot, SourceSnapshot.id == SourceAssertion.source_snapshot_id,
    ).join(
        SourceObject, SourceObject.id == SourceSnapshot.source_object_id,
    ).join(
        DataSource, DataSource.id == SourceObject.source_id,
    ).join(
        CanonicalEntity, CanonicalEntity.wikidata_id == SourceObject.external_id,
    ).where(
        DataSource.name == WIKIDATA_SOURCE_NAME,
        AssertionEvidence.source_assertion_id.is_not(None),
        Assertion.review_status != "retracted",
        ~SourceSnapshot.id.in_(select(latest.c.snapshot_id)),
    )
    if collection_code:
        statement = statement.join(
            ReferenceCollectionMembership,
            ReferenceCollectionMembership.entity_id == CanonicalEntity.id,
        ).where(ReferenceCollectionMembership.collection_code == collection_code)
    assertions = list(db.scalars(statement).unique())
    for assertion in assertions:
        assertion.review_status = "retracted"
    return len(assertions)


def project_source_assertions(
    db: Session,
    *,
    collection_code: str | None = None,
    batch_size: int = 2000,
) -> dict[str, Any]:
    """Project allow-listed facts from current Wikidata snapshots, idempotently."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    latest = _latest_snapshot_subquery()
    retracted = _retract_superseded(db, latest, collection_code)
    stats: dict[str, Any] = {
        "statements_scanned": 0,
        "assertions_created": 0,
        "assertions_reused": 0,
        "assertions_retracted": retracted,
        "targets_created": 0,
        "subject_resolutions_created": 0,
        "skipped_by_outcome": Counter(),
        "skipped_by_property": Counter(),
    }
    cursor: UUID | None = None
    while True:
        statement = select(
            SourceAssertion, SourceSnapshot, SourceObject, CanonicalEntity,
        ).join(
            SourceSnapshot, SourceSnapshot.id == SourceAssertion.source_snapshot_id,
        ).join(
            latest, latest.c.snapshot_id == SourceSnapshot.id,
        ).join(
            SourceObject, SourceObject.id == SourceSnapshot.source_object_id,
        ).join(
            DataSource, DataSource.id == SourceObject.source_id,
        ).join(
            CanonicalEntity, CanonicalEntity.wikidata_id == SourceObject.external_id,
        ).where(DataSource.name == WIKIDATA_SOURCE_NAME)
        if collection_code:
            statement = statement.join(
                ReferenceCollectionMembership,
                ReferenceCollectionMembership.entity_id == CanonicalEntity.id,
            ).where(ReferenceCollectionMembership.collection_code == collection_code)
        if cursor:
            statement = statement.where(SourceAssertion.id > cursor)
        rows = db.execute(statement.order_by(SourceAssertion.id).limit(batch_size)).all()
        if not rows:
            break
        cursor = rows[-1][0].id
        stats["statements_scanned"] += len(rows)
        decisions: dict[UUID, ProjectionDecision] = {}
        for raw, _snapshot, _object, _subject in rows:
            decision = project_wikidata_statement(raw.source_property, raw.raw_value)
            if decision.outcome == "project":
                decisions[raw.id] = decision
            else:
                stats["skipped_by_outcome"][decision.outcome] += 1
                stats["skipped_by_property"][raw.source_property or "<none>"] += 1

        targets, created = _ensure_targets(db, decisions)
        stats["targets_created"] += created
        raw_ids = list(decisions)
        evidence_by_raw_id = {
            evidence.source_assertion_id: evidence
            for evidence in db.scalars(select(AssertionEvidence).where(
                AssertionEvidence.source_assertion_id.in_(raw_ids),
            ))
        } if raw_ids else {}
        resolution_keys = {
            (resolution.source_object_id, resolution.source_snapshot_id, resolution.entity_id)
            for resolution in db.scalars(select(EntityResolution).where(
                EntityResolution.source_snapshot_id.in_({row[1].id for row in rows}),
            ))
        }
        for raw, snapshot, source_object, subject in rows:
            decision = decisions.get(raw.id)
            if not decision:
                continue
            resolution_key = (source_object.id, snapshot.id, subject.id)
            if resolution_key not in resolution_keys:
                db.add(EntityResolution(
                    source_object_id=source_object.id,
                    source_snapshot_id=snapshot.id,
                    entity_id=subject.id,
                    method="wikidata_qid_exact",
                    confidence=1.0,
                    status="resolved",
                    rationale="The source object QID exactly matches the canonical entity QID.",
                ))
                resolution_keys.add(resolution_key)
                stats["subject_resolutions_created"] += 1
            if raw.id in evidence_by_raw_id:
                stats["assertions_reused"] += 1
                continue
            target = targets.get(decision.object_qid or "")
            assertion = Assertion(
                subject_entity_id=subject.id,
                predicate=decision.predicate or "",
                source_property=raw.source_property,
                object_entity_id=target.id if target else None,
                object_entity_kind=target.entity_kind if target else None,
                value_json=decision.value_json,
                qualifiers=raw.raw_qualifiers,
                rank=raw.source_rank,
                assertion_kind="source_fact",
                source_id=source_object.source_id,
                source_reference=snapshot.canonical_url,
                source_revision=snapshot.source_revision,
                derivation_version=PROJECTOR_VERSION,
                review_status=review_status_for_target(decision, target.entity_kind) if target else (decision.review_status or "review_required"),
            )
            db.add(assertion)
            db.add(AssertionEvidence(
                assertion=assertion,
                source_assertion_id=raw.id,
                evidence_type="source_assertion",
                reference=_source_reference(snapshot, raw),
                note=f"Projected by {PROJECTOR_VERSION}; immutable statement locator retained.",
            ))
            stats["assertions_created"] += 1
        db.commit()
    stats["skipped_by_outcome"] = dict(sorted(stats["skipped_by_outcome"].items()))
    stats["skipped_by_property"] = dict(sorted(
        stats["skipped_by_property"].items(), key=lambda item: (-item[1], item[0])
    ))
    return stats


def projection_coverage(db: Session, collection_code: str) -> dict[str, Any]:
    member_ids = select(ReferenceCollectionMembership.entity_id).where(
        ReferenceCollectionMembership.collection_code == collection_code,
        ReferenceCollectionMembership.status == "included",
    )
    total = db.scalar(select(func.count()).select_from(member_ids.subquery())) or 0
    reviewed = db.scalar(select(func.count(func.distinct(Assertion.subject_entity_id))).where(
        Assertion.subject_entity_id.in_(member_ids),
        Assertion.review_status.in_(("resolved", "published")),
    )) or 0
    raw_linked = db.scalar(select(func.count(func.distinct(Assertion.subject_entity_id))).join(
        AssertionEvidence, AssertionEvidence.assertion_id == Assertion.id,
    ).where(
        Assertion.subject_entity_id.in_(member_ids),
        AssertionEvidence.source_assertion_id.is_not(None),
        Assertion.review_status.in_(("resolved", "published", "review_required")),
    )) or 0
    return {
        "collection_code": collection_code,
        "collection_entities": total,
        "entities_with_raw_linked_assertions": raw_linked,
        "raw_linked_coverage_percent": round(raw_linked / total * 100, 2) if total else 0.0,
        "entities_with_reviewed_assertions": reviewed,
        "reviewed_coverage_percent": round(reviewed / total * 100, 2) if total else 0.0,
        "supported_source_properties": len(SOURCE_PROPERTY_RULES),
        "projector_version": PROJECTOR_VERSION,
    }


def render_coverage_html(report: dict[str, Any]) -> str:
    total = int(report["collection_entities"])
    linked = float(report["raw_linked_coverage_percent"])
    reviewed = float(report["reviewed_coverage_percent"])
    return f"""<!doctype html>
<html lang='en'><meta charset='utf-8'><title>CineGraph assertion projection coverage</title>
<style>body{{background:#0b0b12;color:#f4f1ff;font:16px system-ui;margin:0;padding:40px}}main{{max-width:850px;margin:auto}}.card{{background:#171522;border:1px solid #332d4d;border-radius:18px;padding:24px;margin:18px 0}}.bar{{height:18px;background:#29243a;border-radius:99px;overflow:hidden}}.fill{{height:100%;background:linear-gradient(90deg,#8b5cf6,#ec4899)}}small{{color:#aaa3bd}}</style>
<main><small>{html.escape(str(report['projector_version']))}</small><h1>Operational assertion coverage</h1>
<div class='card'><h2>{html.escape(str(report['collection_code']))}</h2><p>{total:,} collection entities</p></div>
<div class='card'><h3>Direct raw evidence links — {linked:.2f}%</h3><div class='bar'><div class='fill' style='width:{linked}%'></div></div><p>{int(report['entities_with_raw_linked_assertions']):,} entities</p></div>
<div class='card'><h3>Reviewed operational assertions — {reviewed:.2f}%</h3><div class='bar'><div class='fill' style='width:{reviewed}%'></div></div><p>{int(report['entities_with_reviewed_assertions']):,} entities</p></div>
<p><small>{int(report['supported_source_properties'])} allow-listed source properties. Narrative passages and embeddings remain candidate evidence, never facts.</small></p></main></html>"""


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Project current raw Wikidata statements into evidence-linked operational assertions.")
    parser.add_argument("--collection")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    run_migrations()
    with SessionLocal() as db:
        stats = project_source_assertions(db, collection_code=args.collection, batch_size=args.batch_size)
        result: dict[str, Any] = {"projection": stats}
        if args.collection:
            result["coverage"] = projection_coverage(db, args.collection)
        if args.report_dir and args.collection:
            args.report_dir.mkdir(parents=True, exist_ok=True)
            json_path = args.report_dir / "source-assertion-projection.json"
            html_path = args.report_dir / "source-assertion-projection.html"
            json_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
            html_path.write_text(render_coverage_html(result["coverage"]), encoding="utf-8")
            result["reports"] = {"json": str(json_path), "html": str(html_path)}
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
