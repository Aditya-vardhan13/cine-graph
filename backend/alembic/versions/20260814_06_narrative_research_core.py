"""Add section-bound narrative passages and reviewable research answers."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_06"
down_revision: Union[str, None] = "20260813_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "narrative_passages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subject_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), sa.ForeignKey("source_snapshots.id"), nullable=False),
        sa.Column("section_locator", sa.String(length=500), nullable=False),
        sa.Column("section_title", sa.String(length=300), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("language_code", sa.String(length=35), nullable=False, server_default="en"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("citation_markers", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("extraction_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_snapshot_id", "section_locator", "ordinal", "content_hash", name="uq_narrative_passage_snapshot_locator"),
    )
    op.create_index("ix_narrative_passages_subject_entity_id", "narrative_passages", ["subject_entity_id"])
    op.create_index("ix_narrative_passages_source_snapshot_id", "narrative_passages", ["source_snapshot_id"])
    op.create_index("ix_narrative_passages_section_locator", "narrative_passages", ["section_locator"])
    op.create_index("ix_narrative_passages_content_hash", "narrative_passages", ["content_hash"])
    op.create_table(
        "research_answers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subject_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("comparison_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id")),
        sa.Column("question_id", sa.String(length=160), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("evidence_class", sa.String(length=40), nullable=False),
        sa.Column("answer_version", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("reviewer", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("subject_entity_id", "question_id", "answer_version", name="uq_research_answer_question_version"),
        sa.CheckConstraint("evidence_class IN ('source_fact', 'narrative_extraction', 'derived_relation', 'attributed_interpretation', 'semantic_candidate')", name="ck_research_answer_evidence_class"),
        sa.CheckConstraint("review_status IN ('draft', 'review_required', 'published', 'retracted')", name="ck_research_answer_review_status"),
    )
    op.create_index("ix_research_answers_subject_entity_id", "research_answers", ["subject_entity_id"])
    op.create_index("ix_research_answers_comparison_entity_id", "research_answers", ["comparison_entity_id"])
    op.create_index("ix_research_answers_question_id", "research_answers", ["question_id"])
    op.create_index("ix_research_answers_review_status", "research_answers", ["review_status"])
    op.create_table(
        "research_answer_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("research_answer_id", sa.Uuid(), sa.ForeignKey("research_answers.id"), nullable=False),
        sa.Column("narrative_passage_id", sa.Uuid(), sa.ForeignKey("narrative_passages.id")),
        sa.Column("source_assertion_id", sa.Uuid(), sa.ForeignKey("source_assertions.id")),
        sa.Column("evidence_locator", sa.String(length=500)),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint("narrative_passage_id IS NOT NULL OR source_assertion_id IS NOT NULL", name="ck_research_answer_evidence_has_target"),
        sa.UniqueConstraint("research_answer_id", "narrative_passage_id", "source_assertion_id", name="uq_research_answer_evidence_target"),
    )
    op.create_index("ix_research_answer_evidence_research_answer_id", "research_answer_evidence", ["research_answer_id"])
    op.create_index("ix_research_answer_evidence_narrative_passage_id", "research_answer_evidence", ["narrative_passage_id"])
    op.create_index("ix_research_answer_evidence_source_assertion_id", "research_answer_evidence", ["source_assertion_id"])


def downgrade() -> None:
    op.drop_table("research_answer_evidence")
    op.drop_table("research_answers")
    op.drop_table("narrative_passages")
