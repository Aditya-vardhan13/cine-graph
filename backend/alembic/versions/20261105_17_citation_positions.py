"""Preserve source-relative citation positions through passages and chunks."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261105_17"
down_revision: Union[str, None] = "20261026_16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "narrative_passages",
        sa.Column("citation_positions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "evidence_chunks",
        sa.Column("citation_positions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("evidence_chunks", "citation_positions")
    op.drop_column("narrative_passages", "citation_positions")
