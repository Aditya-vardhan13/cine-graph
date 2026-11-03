"""Read passages from the newest captured revision of each source object."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NarrativePassage, SourceSnapshot


# A source parser version determines the approved passage extraction for that
# capture adapter. Adding an experimental extraction requires an explicit
# policy change here; it must not become current merely because it was added.
_PREFERRED_EXTRACTION_BY_SOURCE_PARSER = {
    "enwiki-revision-snapshot-v1": "enwiki-section-passages-v1",
    "enwiki-pinned-revision-recovery-v1": "enwiki-section-passages-recovered-v1",
    "tmdb-v3-local-v1": "tmdb-v3-local-v1",
}


def select_current_extraction_versions(source_parser_version: str | None, versions: set[str]) -> set[str]:
    """Choose one approved extraction, or fail closed on ambiguous history."""
    if not versions:
        return set()
    preferred = _PREFERRED_EXTRACTION_BY_SOURCE_PARSER.get(source_parser_version or "")
    if preferred is not None:
        return {preferred} if preferred in versions else set()
    if len(versions) == 1:
        return versions
    raise ValueError(
        "Multiple passage extraction versions exist for an unconfigured source parser: "
        f"{source_parser_version!r} -> {sorted(versions)!r}"
    )


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
    current = [(passage, snapshot) for passage, snapshot in rows
               if newest.get(snapshot.source_object_id) == snapshot.id]
    versions_by_snapshot: dict[UUID, set[str]] = {}
    snapshot_by_id = {}
    for passage, snapshot in current:
        versions_by_snapshot.setdefault(snapshot.id, set()).add(passage.extraction_version)
        snapshot_by_id[snapshot.id] = snapshot
    selected = {
        snapshot_id: select_current_extraction_versions(snapshot.parser_version, versions)
        for snapshot_id, versions in versions_by_snapshot.items()
        for snapshot in [snapshot_by_id[snapshot_id]]
    }
    return [(passage, snapshot) for passage, snapshot in current
            if passage.extraction_version in selected[snapshot.id]]
