"""Restrict the recorded basis URL for narrative approvals to HTTPS."""
from typing import Sequence, Union

from alembic import op


revision: str = "20261106_20"
down_revision: Union[str, None] = "20261106_19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_narrative_use_decision_approval_basis",
        "narrative_use_decisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_narrative_use_decision_approval_basis",
        "narrative_use_decisions",
        "decision != 'approved' OR (decision_basis_url IS NOT NULL "
        "AND decision_basis_url LIKE 'https://%' AND length(trim(decision_notes)) >= 8)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_narrative_use_decision_approval_basis",
        "narrative_use_decisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_narrative_use_decision_approval_basis",
        "narrative_use_decisions",
        "decision != 'approved' OR (decision_basis_url IS NOT NULL "
        "AND length(trim(decision_basis_url)) > 0 AND length(trim(decision_notes)) >= 8)",
    )
