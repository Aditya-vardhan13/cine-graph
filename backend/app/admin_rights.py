"""Local operator review of per-snapshot narrative model-use eligibility."""
from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin_intake import require_operator
from app.db import get_db
from app.models import (
    CanonicalEntity,
    DataSource,
    NarrativePassage,
    NarrativeUseDecision,
    SourceObject,
    SourceSnapshot,
)
from app.services.narrative_use_decisions import (
    SEMANTIC_MODEL_USE,
    latest_decisions,
    next_decision_version,
)


router = APIRouter(prefix="/api/v1/admin/rights", tags=["local-admin-rights"])


class UseDecisionInput(BaseModel):
    decision: str = Field(pattern="^(approved|denied|review_required)$")
    decision_basis_url: str | None = Field(default=None, max_length=1000)
    decision_notes: str = Field(min_length=8, max_length=4000)


def _decision_out(row: NarrativeUseDecision | None) -> dict | None:
    if row is None:
        return None
    return {
        "decision": row.decision,
        "version": row.decision_version,
        "basis_url": row.decision_basis_url,
        "notes": row.decision_notes,
        "reviewer": row.reviewer,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/queue", dependencies=[Depends(require_operator)])
def review_queue(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> dict:
    """List distinct narrative snapshots with source metadata and review context."""
    candidate_ids = (
        select(SourceSnapshot.id.label("id"), func.max(SourceSnapshot.retrieved_at).label("latest_at"))
        .join(NarrativePassage, NarrativePassage.source_snapshot_id == SourceSnapshot.id)
        .where(SourceSnapshot.fetch_status == "success")
        .group_by(SourceSnapshot.id)
        .order_by(func.max(SourceSnapshot.retrieved_at).desc())
        .limit(limit)
        .subquery()
    )
    snapshots = db.execute(
        select(SourceSnapshot, DataSource.name)
        .join(SourceObject, SourceObject.id == SourceSnapshot.source_object_id)
        .join(DataSource, DataSource.id == SourceObject.source_id)
        .where(SourceSnapshot.id.in_(select(candidate_ids.c.id)))
        .order_by(SourceSnapshot.retrieved_at.desc())
    ).all()
    ids = {snapshot.id for snapshot, _source_name in snapshots}
    if not ids:
        return {"use_case": SEMANTIC_MODEL_USE, "items": []}

    passage_rows = db.execute(
        select(
            NarrativePassage.source_snapshot_id,
            CanonicalEntity.canonical_label,
            NarrativePassage.section_locator,
            NarrativePassage.content,
        )
        .join(CanonicalEntity, CanonicalEntity.id == NarrativePassage.subject_entity_id)
        .where(NarrativePassage.source_snapshot_id.in_(ids))
        .order_by(NarrativePassage.source_snapshot_id, NarrativePassage.section_locator,
                  NarrativePassage.ordinal)
    ).all()
    contexts: dict[UUID, dict[str, object]] = {}
    for snapshot_id, film_title, locator, content in passage_rows:
        item = contexts.setdefault(snapshot_id, {"films": set(), "sections": set(), "samples": []})
        item["films"].add(film_title)
        item["sections"].add(locator)
        if len(item["samples"]) < 3:
            item["samples"].append({"section": locator, "excerpt": content[:700]})
    decisions = latest_decisions(db, ids)
    items = []
    for snapshot, source_name in snapshots:
        context = contexts.get(snapshot.id, {})
        items.append({
            "snapshot_id": str(snapshot.id),
            "source_name": source_name,
            "source_url": snapshot.canonical_url,
            "source_revision": snapshot.source_revision,
            "retrieved_at": snapshot.retrieved_at.isoformat() if snapshot.retrieved_at else None,
            "license": snapshot.license,
            "attribution_url": snapshot.attribution_url,
            "content_hash": snapshot.content_hash,
            "films": sorted(context.get("films", set())),
            "section_count": len(context.get("sections", set())),
            "samples": context.get("samples", []),
            "latest_decision": _decision_out(decisions.get(snapshot.id)),
        })
    return {"use_case": SEMANTIC_MODEL_USE, "items": items}


@router.post("/{snapshot_id}", dependencies=[Depends(require_operator)])
def record_decision(
    snapshot_id: UUID,
    payload: UseDecisionInput,
    reviewer: str = Header(alias="x-operator-email"),
    db: Session = Depends(get_db),
) -> dict:
    snapshot = db.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Source snapshot not found")
    if payload.decision == "approved":
        if not snapshot.attribution_url:
            raise HTTPException(status_code=422, detail="Approval requires a retained attribution URL")
        parsed = urlparse(payload.decision_basis_url or "")
        if parsed.scheme != "https" or not parsed.hostname:
            raise HTTPException(status_code=422, detail="Approval requires an HTTPS policy or rights basis URL")
    row = NarrativeUseDecision(
        source_snapshot_id=snapshot_id,
        use_case=SEMANTIC_MODEL_USE,
        decision=payload.decision,
        decision_version=next_decision_version(db, snapshot_id),
        decision_basis_url=payload.decision_basis_url,
        decision_notes=payload.decision_notes.strip(),
        reviewer=reviewer,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A concurrent decision was recorded; refresh the review queue") from exc
    db.refresh(row)
    return {"snapshot_id": str(snapshot_id), "use_case": SEMANTIC_MODEL_USE,
            "latest_decision": _decision_out(row)}
