"""Read passages from the newest captured revision of each source object."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NarrativePassage, SourceSnapshot


def current_passage_rows(
    db: Session, entity_ids: set[UUID],
) -> list[tuple[NarrativePassage, SourceSnapshot]]:
    """Keep source history immutable while excluding superseded revisions from reads."""
    if not entity_ids:
        return []
    rows = db.execute(select(NarrativePassage, SourceSnapshot).join(
        SourceSnapshot, NarrativePassage.source_snapshot_id == SourceSnapshot.id,
    ).where(NarrativePassage.subject_entity_id.in_(entity_ids)).order_by(
        NarrativePassage.subject_entity_id,
        NarrativePassage.section_locator,
        NarrativePassage.ordinal,
    )).all()
    object_ids = {snapshot.source_object_id for _, snapshot in rows}
    if not object_ids:
        return []
    newest: dict[UUID, UUID] = {}
    for snapshot in db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id.in_(object_ids),
        SourceSnapshot.fetch_status == "success",
    ).order_by(SourceSnapshot.source_object_id,
               SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc())):
        newest.setdefault(snapshot.source_object_id, snapshot.id)
    return [(passage, snapshot) for passage, snapshot in rows
            if newest.get(snapshot.source_object_id) == snapshot.id]
