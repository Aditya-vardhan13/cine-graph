from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    merge_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    aliases: Mapped[list[FilmAlias]] = relationship(back_populates="film", cascade="all, delete-orphan")
    credits: Mapped[list[FilmCredit]] = relationship(back_populates="film", cascade="all, delete-orphan")
    genres: Mapped[list[FilmGenre]] = relationship(back_populates="film", cascade="all, delete-orphan")
    provenance: Mapped[list[FilmProvenance]] = relationship(back_populates="film", cascade="all, delete-orphan")


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
    merge_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="published")
    aliases: Mapped[list[PersonAlias]] = relationship(back_populates="person", cascade="all, delete-orphan")
    credits: Mapped[list[FilmCredit]] = relationship(back_populates="person", cascade="all, delete-orphan")
    provenance: Mapped[list[PersonProvenance]] = relationship(back_populates="person", cascade="all, delete-orphan")


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
