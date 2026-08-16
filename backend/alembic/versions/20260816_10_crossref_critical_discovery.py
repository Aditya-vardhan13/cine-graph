"""Allow Crossref as a review-only scholarly discovery provider."""
from typing import Sequence, Union

from alembic import op


revision: str = "20260816_10"
down_revision: Union[str, None] = "20260816_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_critical_candidate_provider", "critical_discovery_candidates", type_="check")
    op.create_check_constraint(
        "ck_critical_candidate_provider",
        "critical_discovery_candidates",
        "provider IN ('openalex', 'crossref')",
    )
    op.drop_constraint("ck_critical_query_provider", "critical_discovery_queries", type_="check")
    op.create_check_constraint(
        "ck_critical_query_provider",
        "critical_discovery_queries",
        "provider IN ('openalex', 'crossref')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_critical_query_provider", "critical_discovery_queries", type_="check")
    op.create_check_constraint(
        "ck_critical_query_provider", "critical_discovery_queries", "provider IN ('openalex')"
    )
    op.drop_constraint("ck_critical_candidate_provider", "critical_discovery_candidates", type_="check")
    op.create_check_constraint(
        "ck_critical_candidate_provider", "critical_discovery_candidates", "provider IN ('openalex')"
    )
