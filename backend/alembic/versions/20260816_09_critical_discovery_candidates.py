"""Add review-queue records for scholarly criticism discovery."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260816_09"
down_revision: Union[str, None] = "20260816_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "critical_discovery_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subject_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), sa.ForeignKey("source_snapshots.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="openalex"),
        sa.Column("provider_work_id", sa.String(length=300), nullable=False),
        sa.Column("query_title", sa.String(length=500), nullable=False),
        sa.Column("candidate_title", sa.String(length=1000), nullable=False),
        sa.Column("candidate_url", sa.String(length=1000), nullable=False),
        sa.Column("match_method", sa.String(length=40), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("reviewer", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("subject_entity_id", "provider", "provider_work_id", name="uq_critical_candidate_subject_provider_work"),
        sa.CheckConstraint("provider IN ('openalex')", name="ck_critical_candidate_provider"),
        sa.CheckConstraint("match_method IN ('title_phrase', 'title_and_abstract_phrase')", name="ck_critical_candidate_match_method"),
        sa.CheckConstraint("review_status IN ('pending', 'accepted', 'rejected', 'promoted')", name="ck_critical_candidate_review_status"),
    )
    op.create_index("ix_critical_discovery_candidates_subject_entity_id", "critical_discovery_candidates", ["subject_entity_id"])
    op.create_index("ix_critical_discovery_candidates_source_snapshot_id", "critical_discovery_candidates", ["source_snapshot_id"])
    op.create_index("ix_critical_discovery_candidates_review_status", "critical_discovery_candidates", ["review_status"])
    op.create_table(
        "critical_discovery_queries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subject_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), sa.ForeignKey("raw_ingestion_runs.id")),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="openalex"),
        sa.Column("query_version", sa.String(length=100), nullable=False),
        sa.Column("query_title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("candidates_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text()),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("subject_entity_id", "provider", "query_version", name="uq_critical_query_subject_provider_version"),
        sa.CheckConstraint("provider IN ('openalex')", name="ck_critical_query_provider"),
        sa.CheckConstraint("status IN ('complete', 'no_candidates', 'skipped_ambiguous', 'failed')", name="ck_critical_query_status"),
    )
    op.create_index("ix_critical_discovery_queries_subject_entity_id", "critical_discovery_queries", ["subject_entity_id"])
    op.create_index("ix_critical_discovery_queries_ingestion_run_id", "critical_discovery_queries", ["ingestion_run_id"])


def downgrade() -> None:
    op.drop_table("critical_discovery_queries")
    op.drop_table("critical_discovery_candidates")
