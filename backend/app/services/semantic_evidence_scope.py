"""Persistence query helpers for narrative text approved for model use."""
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from app.models import EvidenceChunk, NarrativeUseDecision, SourceSnapshot
from app.services.narrative_use_decisions import SEMANTIC_MODEL_USE


def semantically_approved_chunk_ids():
    """Return chunks with a latest approved decision for this exact snapshot."""
    latest_decision = aliased(NarrativeUseDecision)
    latest_version = select(func.max(NarrativeUseDecision.decision_version)).where(
        NarrativeUseDecision.source_snapshot_id == SourceSnapshot.id,
        NarrativeUseDecision.use_case == SEMANTIC_MODEL_USE,
    ).scalar_subquery()
    return select(EvidenceChunk.id).join(
        SourceSnapshot, SourceSnapshot.id == EvidenceChunk.source_snapshot_id,
    ).join(
        latest_decision,
        and_(
            latest_decision.source_snapshot_id == SourceSnapshot.id,
            latest_decision.use_case == SEMANTIC_MODEL_USE,
            latest_decision.decision_version == latest_version,
            latest_decision.decision == "approved",
            latest_decision.decision_basis_url.is_not(None),
            func.length(func.trim(latest_decision.decision_basis_url)) > 0,
            func.length(func.trim(latest_decision.decision_notes)) >= 8,
        ),
    )
