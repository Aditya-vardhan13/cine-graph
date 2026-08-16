"""Add attributed critical-work and interpretation evidence core."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260816_08"
down_revision: Union[str, None] = "20260816_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "critical_works",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), sa.ForeignKey("source_snapshots.id")),
        sa.Column("external_id", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("canonical_url", sa.String(length=800), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("published_on", sa.Date()),
        sa.Column("work_kind", sa.String(length=40), nullable=False),
        sa.Column("rights_scope", sa.String(length=40), nullable=False),
        sa.Column("work_license", sa.String(length=160)),
        sa.Column("attribution_text", sa.Text()),
        sa.Column("language_code", sa.String(length=35), nullable=False, server_default="en"),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="review_required"),
        sa.Column("reviewer", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_id", "external_id", name="uq_critical_work_source_external"),
        sa.CheckConstraint(
            "work_kind IN ('essay', 'review', 'academic_article', 'video_essay', 'creator_statement')",
            name="ck_critical_work_kind",
        ),
        sa.CheckConstraint(
            "rights_scope IN ('full_text_reusable', 'metadata_link_only', 'permissioned', 'private_reference')",
            name="ck_critical_work_rights_scope",
        ),
        sa.CheckConstraint(
            "review_status IN ('draft', 'review_required', 'published', 'retracted')",
            name="ck_critical_work_review_status",
        ),
        sa.CheckConstraint(
            "rights_scope != 'full_text_reusable' OR source_snapshot_id IS NOT NULL",
            name="ck_critical_work_reusable_snapshot",
        ),
    )
    op.create_index("ix_critical_works_source_id", "critical_works", ["source_id"])
    op.create_index("ix_critical_works_source_snapshot_id", "critical_works", ["source_snapshot_id"])
    op.create_index("ix_critical_works_review_status", "critical_works", ["review_status"])

    op.create_table(
        "critical_work_subjects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("critical_work_id", sa.Uuid(), sa.ForeignKey("critical_works.id"), nullable=False),
        sa.Column("entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("subject_role", sa.String(length=30), nullable=False, server_default="primary"),
        sa.UniqueConstraint("critical_work_id", "entity_id", "subject_role", name="uq_critical_work_subject"),
        sa.CheckConstraint(
            "subject_role IN ('primary', 'comparison', 'context')",
            name="ck_critical_work_subject_role",
        ),
    )
    op.create_index("ix_critical_work_subjects_critical_work_id", "critical_work_subjects", ["critical_work_id"])
    op.create_index("ix_critical_work_subjects_entity_id", "critical_work_subjects", ["entity_id"])

    op.create_table(
        "critical_claims",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("critical_work_id", sa.Uuid(), sa.ForeignKey("critical_works.id"), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("comparison_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id")),
        sa.Column("lens", sa.String(length=100), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("source_claim_locator", sa.Text()),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="review_required"),
        sa.Column("reviewer", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "claim_type IN ('interpretive_argument', 'formal_analysis', 'historical_context', 'reception_judgment', 'comparative_argument')",
            name="ck_critical_claim_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('draft', 'review_required', 'published', 'retracted')",
            name="ck_critical_claim_review_status",
        ),
    )
    op.create_index("ix_critical_claims_critical_work_id", "critical_claims", ["critical_work_id"])
    op.create_index("ix_critical_claims_subject_entity_id", "critical_claims", ["subject_entity_id"])
    op.create_index("ix_critical_claims_comparison_entity_id", "critical_claims", ["comparison_entity_id"])
    op.create_index("ix_critical_claims_lens", "critical_claims", ["lens"])
    op.create_index("ix_critical_claims_review_status", "critical_claims", ["review_status"])

    op.create_table(
        "critical_claim_anchors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("critical_claim_id", sa.Uuid(), sa.ForeignKey("critical_claims.id"), nullable=False),
        sa.Column("narrative_passage_id", sa.Uuid(), sa.ForeignKey("narrative_passages.id")),
        sa.Column("source_assertion_id", sa.Uuid(), sa.ForeignKey("source_assertions.id")),
        sa.Column("anchor_relation", sa.String(length=30), nullable=False),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint(
            "anchor_relation IN ('narrative_anchor', 'factual_anchor', 'counterpoint')",
            name="ck_critical_claim_anchor_relation",
        ),
        sa.CheckConstraint(
            "narrative_passage_id IS NOT NULL OR source_assertion_id IS NOT NULL",
            name="ck_critical_claim_anchor_has_target",
        ),
        sa.UniqueConstraint(
            "critical_claim_id", "narrative_passage_id", "source_assertion_id", "anchor_relation",
            name="uq_critical_claim_anchor_target",
        ),
    )
    op.create_index("ix_critical_claim_anchors_critical_claim_id", "critical_claim_anchors", ["critical_claim_id"])
    op.create_index("ix_critical_claim_anchors_narrative_passage_id", "critical_claim_anchors", ["narrative_passage_id"])
    op.create_index("ix_critical_claim_anchors_source_assertion_id", "critical_claim_anchors", ["source_assertion_id"])


def downgrade() -> None:
    op.drop_table("critical_claim_anchors")
    op.drop_table("critical_claims")
    op.drop_table("critical_work_subjects")
    op.drop_table("critical_works")
