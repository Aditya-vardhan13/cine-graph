"""Read and append the versioned narrative-use decision ledger."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import NarrativeUseDecision


SEMANTIC_MODEL_USE = "semantic_index_and_model_input"


def latest_decisions(db: Session, snapshot_ids: set[UUID] | None = None) -> dict[UUID, NarrativeUseDecision]:
    """Return the highest version for each snapshot for the semantic-use purpose."""
    latest = select(
        NarrativeUseDecision.source_snapshot_id.label("snapshot_id"),
        func.max(NarrativeUseDecision.decision_version).label("latest_version"),
    ).where(NarrativeUseDecision.use_case == SEMANTIC_MODEL_USE)
    if snapshot_ids is not None:
        if not snapshot_ids:
            return {}
        latest = latest.where(NarrativeUseDecision.source_snapshot_id.in_(snapshot_ids))
    latest = latest.group_by(NarrativeUseDecision.source_snapshot_id).subquery()
    rows = db.scalars(
        select(NarrativeUseDecision).join(
            latest,
            and_(
                NarrativeUseDecision.source_snapshot_id == latest.c.snapshot_id,
                NarrativeUseDecision.decision_version == latest.c.latest_version,
                NarrativeUseDecision.use_case == SEMANTIC_MODEL_USE,
            ),
        )
    )
    return {row.source_snapshot_id: row for row in rows}


def next_decision_version(db: Session, snapshot_id: UUID) -> int:
    current = db.scalar(select(func.max(NarrativeUseDecision.decision_version)).where(
        NarrativeUseDecision.source_snapshot_id == snapshot_id,
        NarrativeUseDecision.use_case == SEMANTIC_MODEL_USE,
    ))
    return int(current or 0) + 1
