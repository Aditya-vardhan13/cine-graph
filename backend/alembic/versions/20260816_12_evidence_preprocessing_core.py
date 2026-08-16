"""Add versioned, source-linked narrative evidence chunks.

Chunks are intentionally text-only.  A later vector-index migration will
reference these rows instead of modifying raw narrative passages.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260816_12"
down_revision: Union[str, None] = "20260816_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_chunk_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_code", sa.String(length=100), nullable=False),
        sa.Column("language_code", sa.String(length=35), nullable=False),
        sa.Column("chunker_version", sa.String(length=100), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("passages_requested", sa.Integer(), nullable=False),
        sa.Column("passages_eligible", sa.Integer(), nullable=False),
        sa.Column("chunks_created", sa.Integer(), nullable=False),
        sa.Column("chunks_reused", sa.Integer(), nullable=False),
        sa.Column("chunks_excluded", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('running', 'complete', 'failed')", name="ck_evidence_chunk_run_status"),
        sa.ForeignKeyConstraint(["collection_code"], ["reference_collections.code"]),
        sa.ForeignKeyConstraint(["language_code"], ["language_editions.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_code", "language_code", "chunker_version", "configuration_hash",
            name="uq_evidence_chunk_run_configuration",
        ),
    )
    op.create_index("ix_evidence_chunk_runs_collection_code", "evidence_chunk_runs", ["collection_code"])
    op.create_index("ix_evidence_chunk_runs_language_code", "evidence_chunk_runs", ["language_code"])
    op.create_index("ix_evidence_chunk_runs_configuration_hash", "evidence_chunk_runs", ["configuration_hash"])

    op.create_table(
        "evidence_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("preprocessing_run_id", sa.Uuid(), nullable=False),
        sa.Column("narrative_passage_id", sa.Uuid(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("language_code", sa.String(length=35), nullable=False),
        sa.Column("section_locator", sa.Text(), nullable=False),
        sa.Column("section_title", sa.Text(), nullable=False),
        sa.Column("chunk_ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("token_count_estimate", sa.Integer(), nullable=False),
        sa.Column("sentence_count", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=30), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("duplicate_of_chunk_id", sa.Uuid(), nullable=True),
        sa.Column("chunker_version", sa.String(length=100), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "quality_status IN ('eligible', 'duplicate', 'excluded')",
            name="ck_evidence_chunk_quality_status",
        ),
        sa.ForeignKeyConstraint(["duplicate_of_chunk_id"], ["evidence_chunks.id"]),
        sa.ForeignKeyConstraint(["language_code"], ["language_editions.code"]),
        sa.ForeignKeyConstraint(["narrative_passage_id"], ["narrative_passages.id"]),
        sa.ForeignKeyConstraint(["preprocessing_run_id"], ["evidence_chunk_runs.id"]),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["source_snapshots.id"]),
        sa.ForeignKeyConstraint(["subject_entity_id"], ["canonical_entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "narrative_passage_id", "chunk_ordinal", "chunker_version", "configuration_hash",
            name="uq_evidence_chunk_passage_ordinal_version",
        ),
    )
    op.create_index("ix_evidence_chunks_preprocessing_run_id", "evidence_chunks", ["preprocessing_run_id"])
    op.create_index("ix_evidence_chunks_narrative_passage_id", "evidence_chunks", ["narrative_passage_id"])
    op.create_index("ix_evidence_chunks_subject_entity_id", "evidence_chunks", ["subject_entity_id"])
    op.create_index("ix_evidence_chunks_source_snapshot_id", "evidence_chunks", ["source_snapshot_id"])
    op.create_index("ix_evidence_chunks_language_code", "evidence_chunks", ["language_code"])
    op.create_index("ix_evidence_chunks_content_hash", "evidence_chunks", ["content_hash"])
    op.create_index("ix_evidence_chunks_quality_status", "evidence_chunks", ["quality_status"])
    op.create_index("ix_evidence_chunks_duplicate_of_chunk_id", "evidence_chunks", ["duplicate_of_chunk_id"])
    op.create_index("ix_evidence_chunks_configuration_hash", "evidence_chunks", ["configuration_hash"])
    op.create_index(
        "ix_evidence_chunks_retrieval_scope",
        "evidence_chunks",
        ["subject_entity_id", "language_code", "quality_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_chunks_retrieval_scope", table_name="evidence_chunks")
    op.drop_table("evidence_chunks")
    op.drop_table("evidence_chunk_runs")
