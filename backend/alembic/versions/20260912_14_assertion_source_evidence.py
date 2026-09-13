"""Link operational assertions directly to immutable source assertions.

The nullable column preserves every existing evidence row. New raw-source
projections use the unique foreign key so replaying a snapshot cannot publish
the same source statement twice.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260912_14"
down_revision: Union[str, None] = "20260901_13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assertion_evidence",
        sa.Column("source_assertion_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_assertion_evidence_source_assertion_id",
        "assertion_evidence",
        "source_assertions",
        ["source_assertion_id"],
        ["id"],
    )
    op.create_index(
        "ix_assertion_evidence_source_assertion_id",
        "assertion_evidence",
        ["source_assertion_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assertion_evidence_source_assertion_id",
        table_name="assertion_evidence",
    )
    op.drop_constraint(
        "fk_assertion_evidence_source_assertion_id",
        "assertion_evidence",
        type_="foreignkey",
    )
    op.drop_column("assertion_evidence", "source_assertion_id")
