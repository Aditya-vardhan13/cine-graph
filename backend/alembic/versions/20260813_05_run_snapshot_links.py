"""Track immutable snapshots reused by a subsequent ingestion run."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_05"
down_revision: Union[str, None] = "20260813_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_ingestion_run_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ingestion_run_id", sa.Uuid(), sa.ForeignKey("raw_ingestion_runs.id"), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), sa.ForeignKey("source_snapshots.id"), nullable=False),
        sa.Column("disposition", sa.String(length=30), nullable=False, server_default="reused"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("ingestion_run_id", "source_snapshot_id", name="uq_raw_ingestion_run_snapshot"),
    )
    op.create_index("ix_raw_ingestion_run_snapshots_ingestion_run_id", "raw_ingestion_run_snapshots", ["ingestion_run_id"])
    op.create_index("ix_raw_ingestion_run_snapshots_source_snapshot_id", "raw_ingestion_run_snapshots", ["source_snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_raw_ingestion_run_snapshots_source_snapshot_id", table_name="raw_ingestion_run_snapshots")
    op.drop_index("ix_raw_ingestion_run_snapshots_ingestion_run_id", table_name="raw_ingestion_run_snapshots")
    op.drop_table("raw_ingestion_run_snapshots")
