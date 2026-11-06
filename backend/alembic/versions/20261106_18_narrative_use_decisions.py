"""Add immutable per-snapshot narrative model-use decisions."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261106_18"
down_revision: Union[str, None] = "20261105_17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "narrative_use_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("use_case", sa.String(length=60), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("decision_version", sa.Integer(), nullable=False),
        sa.Column("decision_basis_url", sa.String(length=1000), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "use_case IN ('semantic_index_and_model_input')",
            name="ck_narrative_use_decision_use_case",
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'denied', 'review_required')",
            name="ck_narrative_use_decision_status",
        ),
        sa.CheckConstraint("decision_version > 0", name="ck_narrative_use_decision_version_positive"),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["source_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_snapshot_id", "use_case", "decision_version",
            name="uq_narrative_use_decision_version",
        ),
    )
    op.create_index(
        "ix_narrative_use_decision_latest",
        "narrative_use_decisions",
        ["source_snapshot_id", "use_case", "decision_version"],
        unique=False,
    )
    op.execute(
        """CREATE FUNCTION reject_narrative_use_decision_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'narrative use decisions are append-only';
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_narrative_use_decisions_append_only
        BEFORE UPDATE OR DELETE ON narrative_use_decisions
        FOR EACH ROW EXECUTE FUNCTION reject_narrative_use_decision_mutation()"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_narrative_use_decisions_append_only ON narrative_use_decisions")
    op.execute("DROP FUNCTION reject_narrative_use_decision_mutation()")
    op.drop_index("ix_narrative_use_decision_latest", table_name="narrative_use_decisions")
    op.drop_table("narrative_use_decisions")
