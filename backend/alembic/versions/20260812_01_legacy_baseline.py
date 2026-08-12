"""Baseline the pre-evidence-core cinema catalogue schema."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.Uuid:
    return sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "language_editions",
        sa.Column("code", sa.String(length=35), primary_key=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("native_name", sa.String(length=100)),
        sa.Column("script", sa.String(length=50), nullable=False, server_default="Latin"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="planned"),
        sa.Column("transliteration_strategy", sa.String(length=100)),
    )
    op.create_table(
        "data_sources",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("rights_status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "ingestion_batches",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("external_reference", sa.String(length=500)),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_published", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="complete"),
        sa.Column("errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_table(
        "films",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("canonical_title", sa.String(length=300), nullable=False),
        sa.Column("release_date", sa.Date()),
        sa.Column("runtime_minutes", sa.Integer()),
        sa.Column("original_language_code", sa.String(length=35), sa.ForeignKey("language_editions.code"), nullable=False),
        sa.Column("country_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("wikidata_id", sa.String(length=30), unique=True),
        sa.Column("merge_confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "people",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("wikidata_id", sa.String(length=30), unique=True),
        sa.Column("merge_confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="published"),
    )
    op.create_table(
        "genres",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("label", sa.String(length=100), nullable=False, unique=True),
        sa.Column("wikidata_id", sa.String(length=30), unique=True),
    )
    op.create_table(
        "film_aliases",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("value", sa.String(length=300), nullable=False),
        sa.Column("language_code", sa.String(length=35)),
        sa.Column("normalized_value", sa.String(length=300), nullable=False),
        sa.UniqueConstraint("film_id", "value", name="uq_film_alias"),
    )
    op.create_table(
        "person_aliases",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("person_id", _uuid(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("value", sa.String(length=300), nullable=False),
        sa.Column("language_code", sa.String(length=35)),
        sa.Column("normalized_value", sa.String(length=300), nullable=False),
        sa.UniqueConstraint("person_id", "value", name="uq_person_alias"),
    )
    op.create_table(
        "film_credits",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("person_id", _uuid(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("character_name", sa.String(length=300)),
        sa.Column("position", sa.Integer()),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("film_id", "person_id", "role", name="uq_film_credit"),
    )
    op.create_table(
        "film_genres",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("genre_id", _uuid(), sa.ForeignKey("genres.id"), nullable=False),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("film_id", "genre_id", name="uq_film_genre"),
    )
    op.create_table(
        "film_relationships",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("from_film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("to_film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("relationship_type", sa.String(length=60), nullable=False),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("from_film_id", "to_film_id", "relationship_type", name="uq_film_relationship"),
    )
    op.create_table(
        "film_release_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("location_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("event_type", sa.String(length=50), nullable=False, server_default="release"),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("batch_id", _uuid(), sa.ForeignKey("ingestion_batches.id")),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("film_id", "release_date", "source_id", "source_reference", name="uq_film_release_event"),
    )
    op.create_table(
        "external_work_relationships",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("from_film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("to_wikidata_id", sa.String(length=30), nullable=False),
        sa.Column("relationship_type", sa.String(length=60), nullable=False),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("from_film_id", "to_wikidata_id", "relationship_type", "source_id", name="uq_external_work_relationship"),
    )
    op.create_table(
        "corpus_records",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("release_date", sa.Date()),
        sa.Column("language_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("country_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("genres", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("source_revision", sa.String(length=100)),
        sa.Column("raw_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("film_id", _uuid(), sa.ForeignKey("films.id")),
        sa.Column("match_status", sa.String(length=30), nullable=False, server_default="unresolved"),
        sa.Column("match_method", sa.String(length=50)),
        sa.Column("match_confidence", sa.Float()),
        sa.Column("reviewer", sa.String(length=120)),
        sa.UniqueConstraint("source_id", "external_id", name="uq_corpus_record_source_external"),
    )
    op.create_table(
        "narrative_documents",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("corpus_record_id", _uuid(), sa.ForeignKey("corpus_records.id"), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("language_code", sa.String(length=35), nullable=False, server_default="en"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("attribution_url", sa.String(length=500), nullable=False),
        sa.Column("source_revision", sa.String(length=100)),
        sa.Column("access_scope", sa.String(length=50), nullable=False, server_default="attributed_reference"),
        sa.UniqueConstraint("corpus_record_id", "document_type", "content_hash", name="uq_narrative_document"),
    )
    op.create_table(
        "film_provenance",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("film_id", _uuid(), sa.ForeignKey("films.id"), nullable=False),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("batch_id", _uuid(), sa.ForeignKey("ingestion_batches.id")),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
    )
    op.create_table(
        "person_provenance",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("person_id", _uuid(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("batch_id", _uuid(), sa.ForeignKey("ingestion_batches.id")),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
    )
    for table, columns in {
        "films": ["canonical_title", "original_language_code", "wikidata_id"],
        "people": ["canonical_name", "wikidata_id"],
        "film_aliases": ["normalized_value"],
        "person_aliases": ["normalized_value"],
        "film_credits": ["film_id", "person_id", "role"],
        "film_release_events": ["film_id", "release_date"],
        "external_work_relationships": ["from_film_id", "to_wikidata_id", "relationship_type"],
        "corpus_records": ["external_id", "film_id", "match_status"],
        "narrative_documents": ["corpus_record_id", "content_hash"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in [
        "person_provenance", "film_provenance", "narrative_documents", "corpus_records",
        "external_work_relationships", "film_release_events", "film_relationships", "film_genres",
        "film_credits", "person_aliases", "film_aliases", "genres", "people", "films",
        "ingestion_batches", "data_sources", "language_editions",
    ]:
        op.drop_table(table)
