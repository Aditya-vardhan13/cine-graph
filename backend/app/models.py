from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class LanguageEdition(Base):
    __tablename__ = "language_editions"
    code: Mapped[str] = mapped_column(String(35), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_name: Mapped[str | None] = mapped_column(String(100))
    script: Mapped[str] = mapped_column(String(50), nullable=False, default="Latin")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")
    transliteration_strategy: Mapped[str | None] = mapped_column(String(100))


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    license: Mapped[str] = mapped_column(String(100), nullable=False)
    rights_status: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    batches: Mapped[list[IngestionBatch]] = relationship(back_populates="source")


class SourceAccessPolicy(Base):
    """Recorded permission decision for one acquisition route, not a crawler bypass."""

    __tablename__ = "source_access_policies"
    __table_args__ = (
        CheckConstraint("access_mode IN ('api', 'dump', 'html')", name="ck_source_access_policy_mode"),
        CheckConstraint("decision IN ('allowed', 'denied', 'review_required')", name="ck_source_access_policy_decision"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    access_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_url: Mapped[str] = mapped_column(String(500), nullable=False)
    policy_revision: Mapped[str | None] = mapped_column(String(150))
    robots_url: Mapped[str | None] = mapped_column(String(500))
    robots_decision: Mapped[str | None] = mapped_column(String(40))
    allowed_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    required_user_agent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_requests_per_minute: Mapped[int | None] = mapped_column(Integer)
    max_concurrency: Mapped[int | None] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(30), nullable=False, default="review_required")
    decision_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RawIngestionRun(Base):
    """One replayable source run, tied to an input manifest and adapter version."""

    __tablename__ = "raw_ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'complete', 'failed', 'cancelled')", name="ck_raw_ingestion_run_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    access_policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_access_policies.id"), index=True)
    adapter_name: Mapped[str] = mapped_column(String(120), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(100), nullable=False)
    manifest_uri: Mapped[str | None] = mapped_column(String(800))
    manifest_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    input_revision: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    records_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_snapshotted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceObject(Base):
    """Stable identity of an object at a source; multiple snapshots retain its history."""

    __tablename__ = "source_objects"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_object_source_external"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    object_kind: Mapped[str] = mapped_column(String(80), nullable=False, default="work")
    canonical_url: Mapped[str] = mapped_column(String(800), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    snapshots: Mapped[list[SourceSnapshot]] = relationship(back_populates="source_object", cascade="all, delete-orphan")


class SourceSnapshot(Base):
    """Immutable captured source payload descriptor; bytes live in object storage."""

    __tablename__ = "source_snapshots"
    __table_args__ = (
        UniqueConstraint("source_object_id", "source_revision", "content_hash", name="uq_source_snapshot_revision_hash"),
        CheckConstraint("fetch_status IN ('success', 'not_modified', 'not_found', 'denied', 'failed')", name="ck_source_snapshot_fetch_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_object_id: Mapped[UUID] = mapped_column(ForeignKey("source_objects.id"), nullable=False, index=True)
    ingestion_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("raw_ingestion_runs.id"), index=True)
    source_revision: Mapped[str | None] = mapped_column(String(150), index=True)
    canonical_url: Mapped[str] = mapped_column(String(800), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fetch_status: Mapped[str] = mapped_column(String(30), nullable=False, default="success")
    http_status: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    storage_uri: Mapped[str | None] = mapped_column(String(1000))
    license: Mapped[str] = mapped_column(String(100), nullable=False)
    attribution_url: Mapped[str | None] = mapped_column(String(800))
    parser_version: Mapped[str | None] = mapped_column(String(100))
    source_object: Mapped[SourceObject] = relationship(back_populates="snapshots")
    assertions: Mapped[list[SourceAssertion]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class RawIngestionRunSnapshot(Base):
    """Associates a replayed run with both newly created and reused immutable snapshots."""

    __tablename__ = "raw_ingestion_run_snapshots"
    __table_args__ = (UniqueConstraint("ingestion_run_id", "source_snapshot_id", name="uq_raw_ingestion_run_snapshot"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(ForeignKey("raw_ingestion_runs.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("source_snapshots.id"), nullable=False, index=True)
    disposition: Mapped[str] = mapped_column(String(30), nullable=False, default="reused")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceAssertion(Base):
    """Immutable, source-shaped statement before entity resolution or normalization."""

    __tablename__ = "source_assertions"
    __table_args__ = (UniqueConstraint("source_snapshot_id", "statement_locator", "extractor_version", name="uq_source_assertion_locator"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("source_snapshots.id"), nullable=False, index=True)
    statement_locator: Mapped[str] = mapped_column(String(500), nullable=False)
    source_property: Mapped[str | None] = mapped_column(String(100), index=True)
    raw_subject: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    raw_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    raw_qualifiers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_rank: Mapped[str | None] = mapped_column(String(30))
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    snapshot: Mapped[SourceSnapshot] = relationship(back_populates="assertions")


class EntityResolution(Base):
    """A reviewable association between one source object/snapshot and a canonical entity."""

    __tablename__ = "entity_resolutions"
    __table_args__ = (
        UniqueConstraint("source_object_id", "entity_id", "source_snapshot_id", name="uq_entity_resolution"),
        CheckConstraint("status IN ('resolved', 'review_required', 'rejected')", name="ck_entity_resolution_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_object_id: Mapped[UUID] = mapped_column(ForeignKey("source_objects.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_snapshots.id"), index=True)
    entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="review_required")
    reviewer: Mapped[str | None] = mapped_column(String(120))
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Claim(Base):
    """Normalized fact candidate. Claims are not source snapshots and never erase them."""

    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("object_entity_id IS NOT NULL OR value_json IS NOT NULL", name="ck_claim_has_target"),
        CheckConstraint("status IN ('raw', 'resolved', 'published', 'review_required', 'retracted')", name="ck_claim_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    object_entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    object_entity_kind: Mapped[str | None] = mapped_column(String(40), index=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    value_precision: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="raw", index=True)
    normalization_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    evidence: Mapped[list[ClaimEvidence]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    qualifiers: Mapped[list[ClaimQualifier]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class ClaimEvidence(Base):
    """A normalized claim is publishable only through retained source assertion evidence."""

    __tablename__ = "claim_evidence"
    __table_args__ = (UniqueConstraint("claim_id", "source_assertion_id", name="uq_claim_evidence"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    source_assertion_id: Mapped[UUID] = mapped_column(ForeignKey("source_assertions.id"), nullable=False, index=True)
    evidence_note: Mapped[str | None] = mapped_column(Text)
    claim: Mapped[Claim] = relationship(back_populates="evidence")


class ClaimQualifier(Base):
    """Queryable normalised qualifiers; uncommon source detail remains in source assertions."""

    __tablename__ = "claim_qualifiers"
    __table_args__ = (UniqueConstraint("claim_id", "qualifier_key", "value_hash", name="uq_claim_qualifier"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    qualifier_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    claim: Mapped[Claim] = relationship(back_populates="qualifiers")


class CanonicalEntity(Base):
    """Stable identity for any work or person, independent of source and language."""

    __tablename__ = "canonical_entities"
    __table_args__ = (
        CheckConstraint(
            "entity_kind IN ('film', 'person', 'book', 'play', 'comic', 'series', 'episode', 'game', 'organisation', 'place', 'award', 'character', 'unknown_work')",
            name="ck_canonical_entity_kind",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    entity_kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    canonical_label: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    aliases: Mapped[list[EntityAlias]] = relationship(back_populates="entity", cascade="all, delete-orphan")
    film_profile: Mapped[Film | None] = relationship(back_populates="entity")
    person_profile: Mapped[Person | None] = relationship(back_populates="entity")
    subject_assertions: Mapped[list[Assertion]] = relationship(
        back_populates="subject_entity", foreign_keys="Assertion.subject_entity_id", cascade="all, delete-orphan"
    )
    object_assertions: Mapped[list[Assertion]] = relationship(
        back_populates="object_entity", foreign_keys="Assertion.object_entity_id"
    )


class EntityAlias(Base):
    """A source-backed name or title, including future language editions."""

    __tablename__ = "entity_aliases"
    __table_args__ = (UniqueConstraint("entity_id", "value", "language_code", "alias_kind", name="uq_entity_alias"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    language_code: Mapped[str | None] = mapped_column(String(35), index=True)
    script: Mapped[str | None] = mapped_column(String(50))
    alias_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="title")
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id"))
    source_reference: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="published")
    entity: Mapped[CanonicalEntity] = relationship(back_populates="aliases")


class SourceRecord(Base):
    """Immutable source payload descriptor, separate from canonical interpretation."""

    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_record_source_external"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("ingestion_batches.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    source_revision: Mapped[str | None] = mapped_column(String(150))
    payload_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    rights_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="open")
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    assertions: Mapped[list[Assertion]] = relationship(back_populates="source_record")


class Assertion(Base):
    """An inspectable source fact, derivation, or editorial statement."""

    __tablename__ = "assertions"
    __table_args__ = (
        CheckConstraint(
            "assertion_kind IN ('source_fact', 'derived', 'editorial')",
            name="ck_assertion_kind",
        ),
        CheckConstraint(
            "review_status IN ('raw', 'resolved', 'review_required', 'published', 'retracted')",
            name="ck_assertion_review_status",
        ),
        CheckConstraint(
            "object_entity_id IS NOT NULL OR value_json IS NOT NULL",
            name="ck_assertion_has_target",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_property: Mapped[str | None] = mapped_column(String(80), index=True)
    object_entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    object_entity_kind: Mapped[str | None] = mapped_column(String(40), index=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    qualifiers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    rank: Mapped[str | None] = mapped_column(String(30))
    assertion_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="source_fact", index=True)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id"), index=True)
    source_record_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_records.id"), index=True)
    batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("ingestion_batches.id"), index=True)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    source_revision: Mapped[str | None] = mapped_column(String(150))
    derivation_version: Mapped[str | None] = mapped_column(String(100))
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="raw", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    subject_entity: Mapped[CanonicalEntity] = relationship(back_populates="subject_assertions", foreign_keys=[subject_entity_id])
    object_entity: Mapped[CanonicalEntity | None] = relationship(back_populates="object_assertions", foreign_keys=[object_entity_id])
    source_record: Mapped[SourceRecord | None] = relationship(back_populates="assertions")
    evidence: Mapped[list[AssertionEvidence]] = relationship(back_populates="assertion", cascade="all, delete-orphan")


class AssertionEvidence(Base):
    """Additional evidence references for an assertion, including source snippets or documents."""

    __tablename__ = "assertion_evidence"
    __table_args__ = (UniqueConstraint("assertion_id", "evidence_type", "reference", name="uq_assertion_evidence"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assertion_id: Mapped[UUID] = mapped_column(ForeignKey("assertions.id"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    assertion: Mapped[Assertion] = relationship(back_populates="evidence")


class InsightCard(Base):
    """A writer-facing observation with explicit evidence and a derivation policy."""

    __tablename__ = "insight_cards"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'review_required', 'published', 'retracted')",
            name="ck_insight_card_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    writer_question: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    comparison_entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    assertion_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="derived")
    derivation_version: Mapped[str | None] = mapped_column(String(100))
    reviewer: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    evidence: Mapped[list[InsightEvidence]] = relationship(back_populates="insight", cascade="all, delete-orphan")


class InsightEvidence(Base):
    """An insight cannot be published without retained evidence links."""

    __tablename__ = "insight_evidence"
    __table_args__ = (
        CheckConstraint(
            "assertion_id IS NOT NULL OR narrative_document_id IS NOT NULL",
            name="ck_insight_evidence_has_target",
        ),
        UniqueConstraint("insight_id", "assertion_id", "narrative_document_id", name="uq_insight_evidence"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    insight_id: Mapped[UUID] = mapped_column(ForeignKey("insight_cards.id"), nullable=False, index=True)
    assertion_id: Mapped[UUID | None] = mapped_column(ForeignKey("assertions.id"), index=True)
    narrative_document_id: Mapped[UUID | None] = mapped_column(ForeignKey("narrative_documents.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    insight: Mapped[InsightCard] = relationship(back_populates="evidence")


class ReferenceCollection(Base):
    """A transparent, versioned inclusion set; it is never a hidden popularity rank."""

    __tablename__ = "reference_collections"
    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(ForeignKey("language_editions.code"), nullable=False, index=True)
    period_start_year: Mapped[int | None] = mapped_column(Integer)
    period_end_year: Mapped[int | None] = mapped_column(Integer)
    selection_method: Mapped[str] = mapped_column(String(100), nullable=False)
    selection_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    memberships: Mapped[list[ReferenceCollectionMembership]] = relationship(back_populates="collection", cascade="all, delete-orphan")


class ReferenceCollectionMembership(Base):
    """The evidence and selection signals behind one collection membership."""

    __tablename__ = "reference_collection_memberships"
    __table_args__ = (UniqueConstraint("collection_code", "entity_id", name="uq_reference_collection_membership"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    collection_code: Mapped[str] = mapped_column(ForeignKey("reference_collections.code"), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    selection_position: Mapped[int | None] = mapped_column(Integer)
    selection_signals: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="included")
    collection: Mapped[ReferenceCollection] = relationship(back_populates="memberships")


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(500))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    records_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_published: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="complete")
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[DataSource] = relationship(back_populates="batches")


class Film(Base):
    __tablename__ = "films"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    release_date: Mapped[date | None] = mapped_column(Date)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    original_language_code: Mapped[str] = mapped_column(ForeignKey("language_editions.code"), nullable=False, index=True)
    country_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    wikidata_id: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("canonical_entities.id"), unique=True, index=True)
    merge_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    aliases: Mapped[list[FilmAlias]] = relationship(back_populates="film", cascade="all, delete-orphan")
    credits: Mapped[list[FilmCredit]] = relationship(back_populates="film", cascade="all, delete-orphan")
    genres: Mapped[list[FilmGenre]] = relationship(back_populates="film", cascade="all, delete-orphan")
    provenance: Mapped[list[FilmProvenance]] = relationship(back_populates="film", cascade="all, delete-orphan")
    release_events: Mapped[list[FilmReleaseEvent]] = relationship(back_populates="film", cascade="all, delete-orphan")
    corpus_records: Mapped[list[CorpusRecord]] = relationship(back_populates="film")
    entity: Mapped[CanonicalEntity | None] = relationship(back_populates="film_profile")


class FilmAlias(Base):
    __tablename__ = "film_aliases"
    __table_args__ = (UniqueConstraint("film_id", "value", name="uq_film_alias"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False)
    value: Mapped[str] = mapped_column(String(300), nullable=False)
    language_code: Mapped[str | None] = mapped_column(String(35))
    normalized_value: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    film: Mapped[Film] = relationship(back_populates="aliases")


class Person(Base):
    __tablename__ = "people"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("canonical_entities.id"), unique=True, index=True)
    merge_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="published")
    aliases: Mapped[list[PersonAlias]] = relationship(back_populates="person", cascade="all, delete-orphan")
    credits: Mapped[list[FilmCredit]] = relationship(back_populates="person", cascade="all, delete-orphan")
    provenance: Mapped[list[PersonProvenance]] = relationship(back_populates="person", cascade="all, delete-orphan")
    entity: Mapped[CanonicalEntity | None] = relationship(back_populates="person_profile")


class PersonAlias(Base):
    __tablename__ = "person_aliases"
    __table_args__ = (UniqueConstraint("person_id", "value", name="uq_person_alias"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False)
    value: Mapped[str] = mapped_column(String(300), nullable=False)
    language_code: Mapped[str | None] = mapped_column(String(35))
    normalized_value: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    person: Mapped[Person] = relationship(back_populates="aliases")


class FilmCredit(Base):
    __tablename__ = "film_credits"
    __table_args__ = (UniqueConstraint("film_id", "person_id", "role", name="uq_film_credit"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False, index=True)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    character_name: Mapped[str | None] = mapped_column(String(300))
    position: Mapped[int | None] = mapped_column(Integer)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    film: Mapped[Film] = relationship(back_populates="credits")
    person: Mapped[Person] = relationship(back_populates="credits")


class Genre(Base):
    __tablename__ = "genres"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(30), unique=True)


class FilmGenre(Base):
    __tablename__ = "film_genres"
    __table_args__ = (UniqueConstraint("film_id", "genre_id", name="uq_film_genre"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False)
    genre_id: Mapped[UUID] = mapped_column(ForeignKey("genres.id"), nullable=False)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    film: Mapped[Film] = relationship(back_populates="genres")
    genre: Mapped[Genre] = relationship()


class FilmRelationship(Base):
    __tablename__ = "film_relationships"
    __table_args__ = (UniqueConstraint("from_film_id", "to_film_id", "relationship_type", name="uq_film_relationship"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    from_film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False, index=True)
    to_film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)


class FilmReleaseEvent(Base):
    """One source-backed release assertion; Film.release_date is only a display selection."""

    __tablename__ = "film_release_events"
    __table_args__ = (UniqueConstraint("film_id", "release_date", "source_id", "source_reference", name="uq_film_release_event"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False, index=True)
    release_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    location_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, default="release")
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("ingestion_batches.id"))
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    film: Mapped[Film] = relationship(back_populates="release_events")


class ExternalWorkRelationship(Base):
    """Explicit source relationship retained even when its other film is not in the local catalog yet."""

    __tablename__ = "external_work_relationships"
    __table_args__ = (UniqueConstraint("from_film_id", "to_wikidata_id", "relationship_type", "source_id", name="uq_external_work_relationship"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    from_film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False, index=True)
    to_wikidata_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)


class CorpusRecord(Base):
    """A source record that may be reconciled to a canonical film without changing its source meaning."""

    __tablename__ = "corpus_records"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_corpus_record_source_external"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    release_date: Mapped[date | None] = mapped_column(Date)
    language_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    country_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    genres: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_revision: Mapped[str | None] = mapped_column(String(100))
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    film_id: Mapped[UUID | None] = mapped_column(ForeignKey("films.id"), index=True)
    match_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unresolved", index=True)
    match_method: Mapped[str | None] = mapped_column(String(50))
    match_confidence: Mapped[float | None] = mapped_column(Float)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    film: Mapped[Film | None] = relationship(back_populates="corpus_records")
    documents: Mapped[list[NarrativeDocument]] = relationship(back_populates="corpus_record", cascade="all, delete-orphan")


class NarrativeDocument(Base):
    """License-separated narrative material. It is never a substitute for canonical facts."""

    __tablename__ = "narrative_documents"
    __table_args__ = (UniqueConstraint("corpus_record_id", "document_type", "content_hash", name="uq_narrative_document"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    corpus_record_id: Mapped[UUID] = mapped_column(ForeignKey("corpus_records.id"), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    language_code: Mapped[str] = mapped_column(String(35), nullable=False, default="en")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    license: Mapped[str] = mapped_column(String(100), nullable=False)
    attribution_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_revision: Mapped[str | None] = mapped_column(String(100))
    access_scope: Mapped[str] = mapped_column(String(50), nullable=False, default="attributed_reference")
    corpus_record: Mapped[CorpusRecord] = relationship(back_populates="documents")


class NarrativePassage(Base):
    """A locatable, licensed passage extracted from an immutable source snapshot.

    The passage is deliberately not a canonical fact.  It exists so an answer
    about a film can point back to an exact Wikipedia (or future licensed
    source) revision and section instead of treating narrative prose as
    untraceable metadata.
    """

    __tablename__ = "narrative_passages"
    __table_args__ = (
        UniqueConstraint(
            "source_snapshot_id", "section_locator", "ordinal", "content_hash",
            name="uq_narrative_passage_snapshot_locator",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("source_snapshots.id"), nullable=False, index=True)
    # Wikipedia section paths can be exceptionally long, especially when a
    # page nests a descriptive heading beneath several parent headings.
    section_locator: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    section_title: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language_code: Mapped[str] = mapped_column(String(35), nullable=False, default="en")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    citation_markers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    extraction_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchAnswer(Base):
    """A reviewable answer to a declared CineGraph research question.

    `evidence_class` prevents a source fact, a bounded narrative extraction and
    a critic's interpretation from being displayed as equivalent truth claims.
    """

    __tablename__ = "research_answers"
    __table_args__ = (
        UniqueConstraint("subject_entity_id", "question_id", "answer_version", name="uq_research_answer_question_version"),
        CheckConstraint(
            "evidence_class IN ('source_fact', 'narrative_extraction', 'derived_relation', 'attributed_interpretation', 'semantic_candidate')",
            name="ck_research_answer_evidence_class",
        ),
        CheckConstraint(
            "review_status IN ('draft', 'review_required', 'published', 'retracted')",
            name="ck_research_answer_review_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    comparison_entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    question_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_class: Mapped[str] = mapped_column(String(40), nullable=False)
    answer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    evidence: Mapped[list[ResearchAnswerEvidence]] = relationship(back_populates="answer_record", cascade="all, delete-orphan")


class ResearchAnswerEvidence(Base):
    """One precise passage or structured assertion supporting a research answer."""

    __tablename__ = "research_answer_evidence"
    __table_args__ = (
        CheckConstraint(
            "narrative_passage_id IS NOT NULL OR source_assertion_id IS NOT NULL",
            name="ck_research_answer_evidence_has_target",
        ),
        UniqueConstraint(
            "research_answer_id", "narrative_passage_id", "source_assertion_id",
            name="uq_research_answer_evidence_target",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    research_answer_id: Mapped[UUID] = mapped_column(ForeignKey("research_answers.id"), nullable=False, index=True)
    narrative_passage_id: Mapped[UUID | None] = mapped_column(ForeignKey("narrative_passages.id"), index=True)
    source_assertion_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_assertions.id"), index=True)
    evidence_locator: Mapped[str | None] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)
    answer_record: Mapped[ResearchAnswer] = relationship(back_populates="evidence")


class CriticalWork(Base):
    """An attributed essay, review, scholarly article, or video-essay record.

    A critical work is deliberately distinct from a source fact and from a
    CineGraph answer.  Link-only records carry metadata and a route to the
    original; reusable full text is represented by a separately licensed,
    immutable ``SourceSnapshot``.  This prevents a platform licence (for
    example, a hosting site's licence to display a creator's work) from being
    mistaken for a licence granted to CineGraph.
    """

    __tablename__ = "critical_works"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_critical_work_source_external"),
        CheckConstraint(
            "work_kind IN ('essay', 'review', 'academic_article', 'video_essay', 'creator_statement')",
            name="ck_critical_work_kind",
        ),
        CheckConstraint(
            "rights_scope IN ('full_text_reusable', 'metadata_link_only', 'permissioned', 'private_reference')",
            name="ck_critical_work_rights_scope",
        ),
        CheckConstraint(
            "review_status IN ('draft', 'review_required', 'published', 'retracted')",
            name="ck_critical_work_review_status",
        ),
        CheckConstraint(
            "rights_scope != 'full_text_reusable' OR source_snapshot_id IS NOT NULL",
            name="ck_critical_work_reusable_snapshot",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_snapshots.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(800), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    published_on: Mapped[date | None] = mapped_column(Date)
    work_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    rights_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    work_license: Mapped[str | None] = mapped_column(String(160))
    attribution_text: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str] = mapped_column(String(35), nullable=False, default="en")
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="review_required", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    subjects: Mapped[list[CriticalWorkSubject]] = relationship(back_populates="critical_work", cascade="all, delete-orphan")
    claims: Mapped[list[CriticalClaim]] = relationship(back_populates="critical_work", cascade="all, delete-orphan")


class CriticalWorkSubject(Base):
    """A work's primary film and any comparison/context films it discusses."""

    __tablename__ = "critical_work_subjects"
    __table_args__ = (
        UniqueConstraint("critical_work_id", "entity_id", "subject_role", name="uq_critical_work_subject"),
        CheckConstraint(
            "subject_role IN ('primary', 'comparison', 'context')",
            name="ck_critical_work_subject_role",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    critical_work_id: Mapped[UUID] = mapped_column(ForeignKey("critical_works.id"), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    subject_role: Mapped[str] = mapped_column(String(30), nullable=False, default="primary")
    critical_work: Mapped[CriticalWork] = relationship(back_populates="subjects")


class CriticalClaim(Base):
    """A reviewable, attributed interpretation stated in CineGraph's own words.

    ``claim_text`` is an editorial paraphrase, not copied article prose.  The
    original is located by ``source_claim_locator`` and shown as an attributed
    route.  The claim may be anchored to retained narrative or factual evidence
    without converting the critic's interpretation into a canonical fact.
    """

    __tablename__ = "critical_claims"
    __table_args__ = (
        CheckConstraint(
            "claim_type IN ('interpretive_argument', 'formal_analysis', 'historical_context', 'reception_judgment', 'comparative_argument')",
            name="ck_critical_claim_type",
        ),
        CheckConstraint(
            "review_status IN ('draft', 'review_required', 'published', 'retracted')",
            name="ck_critical_claim_review_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    critical_work_id: Mapped[UUID] = mapped_column(ForeignKey("critical_works.id"), nullable=False, index=True)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    comparison_entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    lens: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(40), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_claim_locator: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="review_required", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    critical_work: Mapped[CriticalWork] = relationship(back_populates="claims")
    anchors: Mapped[list[CriticalClaimAnchor]] = relationship(back_populates="critical_claim", cascade="all, delete-orphan")


class CriticalClaimAnchor(Base):
    """A fact or passage which gives a critic's argument inspectable context."""

    __tablename__ = "critical_claim_anchors"
    __table_args__ = (
        CheckConstraint(
            "anchor_relation IN ('narrative_anchor', 'factual_anchor', 'counterpoint')",
            name="ck_critical_claim_anchor_relation",
        ),
        CheckConstraint(
            "narrative_passage_id IS NOT NULL OR source_assertion_id IS NOT NULL",
            name="ck_critical_claim_anchor_has_target",
        ),
        UniqueConstraint(
            "critical_claim_id", "narrative_passage_id", "source_assertion_id", "anchor_relation",
            name="uq_critical_claim_anchor_target",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    critical_claim_id: Mapped[UUID] = mapped_column(ForeignKey("critical_claims.id"), nullable=False, index=True)
    narrative_passage_id: Mapped[UUID | None] = mapped_column(ForeignKey("narrative_passages.id"), index=True)
    source_assertion_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_assertions.id"), index=True)
    anchor_relation: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    critical_claim: Mapped[CriticalClaim] = relationship(back_populates="anchors")


class CriticalDiscoveryCandidate(Base):
    """A scholarly-metadata lead, not an admitted critical work or a claim.

    The candidate is created from an immutable scholarly-metadata snapshot after
    a conservative film-title match. It must be reviewed for subject fit and
    the *actual work's* licence before promotion into ``CriticalWork``.
    """

    __tablename__ = "critical_discovery_candidates"
    __table_args__ = (
        UniqueConstraint("subject_entity_id", "provider", "provider_work_id", name="uq_critical_candidate_subject_provider_work"),
        CheckConstraint("provider IN ('openalex', 'crossref')", name="ck_critical_candidate_provider"),
        CheckConstraint(
            "match_method IN ('title_phrase', 'title_and_abstract_phrase')",
            name="ck_critical_candidate_match_method",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'accepted', 'rejected', 'promoted')",
            name="ck_critical_candidate_review_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("source_snapshots.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="openalex")
    provider_work_id: Mapped[str] = mapped_column(String(300), nullable=False)
    query_title: Mapped[str] = mapped_column(String(500), nullable=False)
    candidate_title: Mapped[str] = mapped_column(String(1000), nullable=False)
    candidate_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    match_method: Mapped[str] = mapped_column(String(40), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CriticalDiscoveryQuery(Base):
    """One replayable discovery decision, including zero-result and skipped titles."""

    __tablename__ = "critical_discovery_queries"
    __table_args__ = (
        UniqueConstraint("subject_entity_id", "provider", "query_version", name="uq_critical_query_subject_provider_version"),
        CheckConstraint("provider IN ('openalex', 'crossref')", name="ck_critical_query_provider"),
        CheckConstraint(
            "status IN ('complete', 'no_candidates', 'skipped_ambiguous', 'failed')",
            name="ck_critical_query_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_entity_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_entities.id"), nullable=False, index=True)
    ingestion_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("raw_ingestion_runs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="openalex")
    query_version: Mapped[str] = mapped_column(String(100), nullable=False)
    query_title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    candidates_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FilmProvenance(Base):
    __tablename__ = "film_provenance"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    film_id: Mapped[UUID] = mapped_column(ForeignKey("films.id"), nullable=False)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("ingestion_batches.id"))
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    film: Mapped[Film] = relationship(back_populates="provenance")


class PersonProvenance(Base):
    __tablename__ = "person_provenance"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("ingestion_batches.id"))
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    person: Mapped[Person] = relationship(back_populates="provenance")
