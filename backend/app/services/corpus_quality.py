"""Read-only coverage accounting; source registration is not acquired evidence."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Assertion, CorpusRecord, CriticalClaim, CriticalDiscoveryCandidate, CriticalWork,
    DataSource, EvidenceChunk, EvidenceEmbedding, ExternalWorkRelationship, Film,
    FilmReleaseEvent, NarrativeDocument, NarrativePassage, ReferenceCollectionMembership,
    SourceObject, SourceSnapshot,
)
from app.services.retrieval_scope import resolve_retrieval_scope


def corpus_quality_report(db: Session, *, collection_code: str) -> dict:
    def scalar(statement):
        return db.scalar(statement) or 0

    # Fixed query count as sources grow; never a query per source.
    records = {row[0]: row[1:] for row in db.execute(select(
        CorpusRecord.source_id, func.count(),
        func.count().filter(CorpusRecord.match_status == "matched"),
        func.count().filter(CorpusRecord.match_status == "review_required"),
    ).group_by(CorpusRecord.source_id))}
    documents = dict(db.execute(select(CorpusRecord.source_id, func.count())
        .join(NarrativeDocument, NarrativeDocument.corpus_record_id == CorpusRecord.id)
        .group_by(CorpusRecord.source_id)).all())
    passages = {row[0]: row[1:] for row in db.execute(select(
        SourceObject.source_id, func.count(NarrativePassage.id),
        func.count(func.distinct(NarrativePassage.subject_entity_id)),
    ).select_from(SourceObject).join(SourceSnapshot)
        .join(NarrativePassage).group_by(SourceObject.source_id))}
    snapshots = dict(db.execute(select(SourceObject.source_id, func.count())
        .join(SourceSnapshot).where(SourceSnapshot.fetch_status.in_(("success", "not_modified")))
        .group_by(SourceObject.source_id)).all())
    works = dict(db.execute(select(CriticalWork.source_id, func.count())
        .group_by(CriticalWork.source_id)).all())
    sources = []
    for source in db.scalars(select(DataSource).order_by(DataSource.name)):
        source_records, matched, pending = records.get(source.id, (0, 0, 0))
        passage_count, passage_films = passages.get(source.id, (0, 0))
        sources.append(dict(
            source_name=source.name, license=source.license, records=source_records,
            matched=matched, review_required=pending, narrative_documents=documents.get(source.id, 0),
            narrative_passages=passage_count, narrative_films=passage_films,
            source_snapshots=snapshots.get(source.id, 0), critical_works=works.get(source.id, 0),
        ))
    members = select(ReferenceCollectionMembership.entity_id).where(
        ReferenceCollectionMembership.collection_code == collection_code,
    )
    try:
        scope = resolve_retrieval_scope(db, collection_code=collection_code)
    except ValueError:
        scope = None
    narrative = db.execute(select(func.count(), func.count(func.distinct(NarrativePassage.subject_entity_id)))
        .where(NarrativePassage.subject_entity_id.in_(members))).one()
    assertions = db.execute(select(
        func.count().filter(Assertion.review_status.in_(("resolved", "published"))),
        func.count(func.distinct(Assertion.subject_entity_id)).filter(
            Assertion.review_status.in_(("resolved", "published"))),
        func.count().filter(Assertion.review_status == "review_required"),
    ).where(Assertion.subject_entity_id.in_(members))).one()
    indexed_chunks, indexed_films = (0, 0)
    if scope and scope.index_run:
        indexed_chunks, indexed_films = db.execute(select(
            func.count(), func.count(func.distinct(EvidenceChunk.subject_entity_id)),
        ).select_from(EvidenceEmbedding).join(EvidenceChunk)
            .where(EvidenceEmbedding.index_run_id == scope.index_run.id,
                   EvidenceChunk.preprocessing_run_id == scope.preprocessing_run_id,
                   EvidenceChunk.subject_entity_id.in_(members), EvidenceChunk.quality_status == "eligible")).one()
    research = dict(
        collection_code=collection_code,
        films=scalar(select(func.count()).select_from(ReferenceCollectionMembership).where(
            ReferenceCollectionMembership.collection_code == collection_code)),
        narrative_passages=narrative[0], films_with_passages=narrative[1],
        resolved_assertions=assertions[0], films_with_resolved_assertions=assertions[1],
        assertions_requiring_review=assertions[2],
        legacy_profile_films=scalar(select(func.count()).select_from(Film).where(Film.entity_id.in_(members))),
        preprocessing_run_id=str(scope.preprocessing_run_id) if scope else None,
        index_run_id=str(scope.index_run.id) if scope and scope.index_run else None,
        indexed_chunks=indexed_chunks, indexed_films=indexed_films,
    )
    return dict(
        films=scalar(select(func.count()).select_from(Film)),
        release_events=scalar(select(func.count()).select_from(FilmReleaseEvent)),
        explicit_work_relationships=scalar(select(func.count()).select_from(ExternalWorkRelationship)),
        sources=sources, research=research,
        critical_works=scalar(select(func.count()).select_from(CriticalWork)),
        critical_claims=scalar(select(func.count()).select_from(CriticalClaim)),
        pending_critical_candidates=scalar(select(func.count()).select_from(CriticalDiscoveryCandidate)
            .where(CriticalDiscoveryCandidate.review_status == "pending")),
    )
