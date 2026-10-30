"""Allow two extraction algorithms to retain the same source passage text."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261026_16"
down_revision: Union[str, None] = "20261005_15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_narrative_passage_snapshot_locator", "narrative_passages", type_="unique")
    op.create_unique_constraint(
        "uq_narrative_passage_snapshot_locator", "narrative_passages",
        ["source_snapshot_id", "section_locator", "ordinal", "content_hash", "extraction_version"],
    )


def downgrade() -> None:
    duplicate = op.get_bind().execute(sa.text("""
        SELECT 1 FROM narrative_passages
        GROUP BY source_snapshot_id, section_locator, ordinal, content_hash
        HAVING count(*) > 1 LIMIT 1
    """)).first()
    if duplicate is not None:
        raise RuntimeError("Cannot downgrade: multiple extraction versions share a passage identity.")
    op.drop_constraint("uq_narrative_passage_snapshot_locator", "narrative_passages", type_="unique")
    op.create_unique_constraint(
        "uq_narrative_passage_snapshot_locator", "narrative_passages",
        ["source_snapshot_id", "section_locator", "ordinal", "content_hash"],
    )
