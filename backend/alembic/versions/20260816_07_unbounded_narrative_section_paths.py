"""Permit full, exact source section paths in narrative evidence."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260816_07"
down_revision: Union[str, None] = "20260814_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("narrative_passages", "section_locator", type_=sa.Text(), existing_type=sa.String(length=500))
    op.alter_column("narrative_passages", "section_title", type_=sa.Text(), existing_type=sa.String(length=300))


def downgrade() -> None:
    op.alter_column("narrative_passages", "section_title", type_=sa.String(length=300), existing_type=sa.Text())
    op.alter_column("narrative_passages", "section_locator", type_=sa.String(length=500), existing_type=sa.Text())
