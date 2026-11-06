"""Local operator review of per-snapshot narrative model-use eligibility."""
from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

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
def review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    film_q: str | None = Query(default=None, min_length=1, max_length=120),
    review_state: str = Query(default="all", pattern="^(all|unreviewed|approved|denied|review_required)$"),
    db: Session = Depends(get_db),
) -> dict:
    """List narrative snapshots with optional film and latest-decision filters."""
    normalized_film_q = (film_q or "").strip()
    latest_version = (
        select(
            NarrativeUseDecision.source_snapshot_id.label("snapshot_id"),
            func.max(NarrativeUseDecision.decision_version).label("version"),
        )
        .where(NarrativeUseDecision.use_case == SEMANTIC_MODEL_USE)
        .group_by(NarrativeUseDecision.source_snapshot_id)
        .subquery()
    )
    latest_decision = aliased(NarrativeUseDecision)
    passages_for_snapshot = select(1).select_from(NarrativePassage).join(
        CanonicalEntity, CanonicalEntity.id == NarrativePassage.subject_entity_id,
    ).where(NarrativePassage.source_snapshot_id == SourceSnapshot.id)
    if normalized_film_q:
        escaped_query = normalized_film_q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        passages_for_snapshot = passages_for_snapshot.where(
            CanonicalEntity.canonical_label.ilike(f"%{escaped_query}%", escape="\\"),
        )
    filtered = (
        select(SourceSnapshot.id.label("id"), SourceSnapshot.retrieved_at.label("latest_at"))
        .outerjoin(latest_version, latest_version.c.snapshot_id == SourceSnapshot.id)
        .outerjoin(latest_decision, and_(
            latest_decision.source_snapshot_id == SourceSnapshot.id,
            latest_decision.decision_version == latest_version.c.version,
            latest_decision.use_case == SEMANTIC_MODEL_USE,
        ))
        .where(SourceSnapshot.fetch_status == "success", passages_for_snapshot.exists())
    )
    if review_state == "unreviewed":
        filtered = filtered.where(latest_decision.id.is_(None))
    elif review_state != "all":
        filtered = filtered.where(latest_decision.decision == review_state)
    total = db.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    candidate_ids = (
        filtered
        .order_by(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id)
        .offset(offset)
        .limit(limit)
        .subquery()
    )
    snapshots = db.execute(
        select(SourceSnapshot, DataSource.name)
        .join(SourceObject, SourceObject.id == SourceSnapshot.source_object_id)
        .join(DataSource, DataSource.id == SourceObject.source_id)
        .join(candidate_ids, candidate_ids.c.id == SourceSnapshot.id)
        .order_by(candidate_ids.c.latest_at.desc(), SourceSnapshot.id)
    ).all()
    ids = {snapshot.id for snapshot, _source_name in snapshots}
    if not ids:
        return {"use_case": SEMANTIC_MODEL_USE, "items": [],
                "total": total, "offset": offset, "limit": limit,
                "film_q": normalized_film_q, "review_state": review_state}

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
    return {"use_case": SEMANTIC_MODEL_USE, "items": items,
            "total": total, "offset": offset, "limit": limit,
            "film_q": normalized_film_q, "review_state": review_state}


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
