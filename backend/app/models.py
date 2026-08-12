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


class CanonicalEntity(Base):
    """Stable identity for any work or person, independent of source and language."""

    __tablename__ = "canonical_entities"
    __table_args__ = (
        CheckConstraint(
            "entity_kind IN ('film', 'person', 'book', 'play', 'comic', 'series', 'episode', 'game', 'organisation', 'unknown_work')",
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
