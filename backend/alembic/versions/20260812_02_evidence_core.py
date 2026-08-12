"""Add the stable typed evidence core without changing legacy catalogue rows."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_02"
down_revision: Union[str, None] = "20260812_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.Uuid:
    return sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "canonical_entities",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("entity_kind", sa.String(length=40), nullable=False),
        sa.Column("canonical_label", sa.String(length=300), nullable=False),
        sa.Column("wikidata_id", sa.String(length=30), unique=True),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "entity_kind IN ('film', 'person', 'book', 'play', 'comic', 'series', 'episode', 'game', 'organisation', 'unknown_work')",
            name="ck_canonical_entity_kind",
        ),
    )
    op.create_table(
        "entity_aliases",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("entity_id", _uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("value", sa.String(length=300), nullable=False),
        sa.Column("normalized_value", sa.String(length=300), nullable=False),
        sa.Column("language_code", sa.String(length=35)),
        sa.Column("script", sa.String(length=50)),
        sa.Column("alias_kind", sa.String(length=50), nullable=False, server_default="title"),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id")),
        sa.Column("source_reference", sa.String(length=500)),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="published"),
        sa.UniqueConstraint("entity_id", "value", "language_code", "alias_kind", name="uq_entity_alias"),
    )
    op.create_table(
        "source_records",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("batch_id", _uuid(), sa.ForeignKey("ingestion_batches.id")),
        sa.Column("external_id", sa.String(length=300), nullable=False),
        sa.Column("source_revision", sa.String(length=150)),
        sa.Column("payload_hash", sa.String(length=64)),
        sa.Column("rights_scope", sa.String(length=80), nullable=False, server_default="open"),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_record_source_external"),
    )
    op.create_table(
        "assertions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("subject_entity_id", _uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("predicate", sa.String(length=80), nullable=False),
        sa.Column("source_property", sa.String(length=80)),
        sa.Column("object_entity_id", _uuid(), sa.ForeignKey("canonical_entities.id")),
        sa.Column("object_entity_kind", sa.String(length=40)),
        sa.Column("value_json", sa.JSON()),
        sa.Column("qualifiers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("rank", sa.String(length=30)),
        sa.Column("assertion_kind", sa.String(length=30), nullable=False, server_default="source_fact"),
        sa.Column("source_id", _uuid(), sa.ForeignKey("data_sources.id")),
        sa.Column("source_record_id", _uuid(), sa.ForeignKey("source_records.id")),
        sa.Column("batch_id", _uuid(), sa.ForeignKey("ingestion_batches.id")),
        sa.Column("source_reference", sa.String(length=500)),
        sa.Column("source_revision", sa.String(length=150)),
        sa.Column("derivation_version", sa.String(length=100)),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="raw"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("assertion_kind IN ('source_fact', 'derived', 'editorial')", name="ck_assertion_kind"),
        sa.CheckConstraint(
            "review_status IN ('raw', 'resolved', 'review_required', 'published', 'retracted')",
            name="ck_assertion_review_status",
        ),
        sa.CheckConstraint("object_entity_id IS NOT NULL OR value_json IS NOT NULL", name="ck_assertion_has_target"),
    )
    op.create_table(
        "assertion_evidence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("assertion_id", _uuid(), sa.ForeignKey("assertions.id"), nullable=False),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("reference", sa.String(length=500), nullable=False),
        sa.Column("note", sa.Text()),
        sa.UniqueConstraint("assertion_id", "evidence_type", "reference", name="uq_assertion_evidence"),
    )
    op.create_table(
        "insight_cards",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("writer_question", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("subject_entity_id", _uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("comparison_entity_id", _uuid(), sa.ForeignKey("canonical_entities.id")),
        sa.Column("assertion_kind", sa.String(length=30), nullable=False, server_default="derived"),
        sa.Column("derivation_version", sa.String(length=100)),
        sa.Column("reviewer", sa.String(length=120)),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('draft', 'review_required', 'published', 'retracted')", name="ck_insight_card_status"),
    )
    op.create_table(
        "insight_evidence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("insight_id", _uuid(), sa.ForeignKey("insight_cards.id"), nullable=False),
        sa.Column("assertion_id", _uuid(), sa.ForeignKey("assertions.id")),
        sa.Column("narrative_document_id", _uuid(), sa.ForeignKey("narrative_documents.id")),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint(
            "assertion_id IS NOT NULL OR narrative_document_id IS NOT NULL",
            name="ck_insight_evidence_has_target",
        ),
        sa.UniqueConstraint("insight_id", "assertion_id", "narrative_document_id", name="uq_insight_evidence"),
    )
    for table, columns in {
        "canonical_entities": ["entity_kind", "canonical_label", "wikidata_id"],
        "entity_aliases": ["entity_id", "normalized_value", "language_code"],
        "source_records": ["source_id", "batch_id", "external_id", "payload_hash"],
        "assertions": [
            "subject_entity_id", "predicate", "source_property", "object_entity_id", "object_entity_kind",
            "assertion_kind", "source_id", "source_record_id", "batch_id", "review_status",
        ],
        "assertion_evidence": ["assertion_id"],
        "insight_cards": ["kind", "subject_entity_id", "comparison_entity_id", "status"],
        "insight_evidence": ["insight_id", "assertion_id", "narrative_document_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.add_column("films", sa.Column("entity_id", _uuid(), nullable=True))
    op.add_column("people", sa.Column("entity_id", _uuid(), nullable=True))
    op.create_index("ix_films_entity_id", "films", ["entity_id"], unique=True)
    op.create_index("ix_people_entity_id", "people", ["entity_id"], unique=True)
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key("fk_films_entity_id", "films", "canonical_entities", ["entity_id"], ["id"])
        op.create_foreign_key("fk_people_entity_id", "people", "canonical_entities", ["entity_id"], ["id"])


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_people_entity_id", "people", type_="foreignkey")
        op.drop_constraint("fk_films_entity_id", "films", type_="foreignkey")
    op.drop_index("ix_people_entity_id", table_name="people")
    op.drop_index("ix_films_entity_id", table_name="films")
    op.drop_column("people", "entity_id")
    op.drop_column("films", "entity_id")
    for table in [
        "insight_evidence", "insight_cards", "assertion_evidence", "assertions",
        "source_records", "entity_aliases", "canonical_entities",
    ]:
        op.drop_table(table)
