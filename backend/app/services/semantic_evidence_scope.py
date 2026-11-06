"""Persistence query helpers for narrative text approved for model use."""
from sqlalchemy import select

from app.models import DataSource, EvidenceChunk, SourceObject, SourceSnapshot


def semantically_approved_chunk_ids():
    """Return chunk IDs whose source explicitly permits semantic/model use."""
    return select(EvidenceChunk.id).join(
        SourceSnapshot, SourceSnapshot.id == EvidenceChunk.source_snapshot_id,
    ).join(
        SourceObject, SourceObject.id == SourceSnapshot.source_object_id,
    ).join(
        DataSource, DataSource.id == SourceObject.source_id,
    ).where(DataSource.rights_status == "semantic_use_approved")
