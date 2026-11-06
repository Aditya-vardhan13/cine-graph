"""Require a recorded basis and rationale for narrative-use approvals."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261106_19"
down_revision: Union[str, None] = "20261106_18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_narrative_use_decision_approval_basis",
        "narrative_use_decisions",
        "decision != 'approved' OR (decision_basis_url IS NOT NULL "
        "AND length(trim(decision_basis_url)) > 0 AND length(trim(decision_notes)) >= 8)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_narrative_use_decision_approval_basis",
        "narrative_use_decisions",
        type_="check",
    )
