"""Add transparent reference collections and broaden typed graph entities."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_03"
down_revision: Union[str, None] = "20260812_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.Uuid:
    return sa.Uuid()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("ck_canonical_entity_kind", "canonical_entities", type_="check")
        op.create_check_constraint(
            "ck_canonical_entity_kind",
            "canonical_entities",
            "entity_kind IN ('film', 'person', 'book', 'play', 'comic', 'series', 'episode', 'game', 'organisation', 'place', 'award', 'character', 'unknown_work')",
        )
    op.create_table(
        "reference_collections",
        sa.Column("code", sa.String(length=100), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(length=35), sa.ForeignKey("language_editions.code"), nullable=False),
        sa.Column("period_start_year", sa.Integer()),
        sa.Column("period_end_year", sa.Integer()),
        sa.Column("selection_method", sa.String(length=100), nullable=False),
        sa.Column("selection_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "reference_collection_memberships",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("collection_code", sa.String(length=100), sa.ForeignKey("reference_collections.code"), nullable=False),
        sa.Column("entity_id", _uuid(), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("selection_position", sa.Integer()),
        sa.Column("selection_signals", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="included"),
        sa.UniqueConstraint("collection_code", "entity_id", name="uq_reference_collection_membership"),
    )
    op.create_index("ix_reference_collections_language_code", "reference_collections", ["language_code"])
    op.create_index("ix_reference_collection_memberships_collection_code", "reference_collection_memberships", ["collection_code"])
    op.create_index("ix_reference_collection_memberships_entity_id", "reference_collection_memberships", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_reference_collection_memberships_entity_id", table_name="reference_collection_memberships")
    op.drop_index("ix_reference_collection_memberships_collection_code", table_name="reference_collection_memberships")
    op.drop_index("ix_reference_collections_language_code", table_name="reference_collections")
    op.drop_table("reference_collection_memberships")
    op.drop_table("reference_collections")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("ck_canonical_entity_kind", "canonical_entities", type_="check")
        op.create_check_constraint(
            "ck_canonical_entity_kind",
            "canonical_entities",
            "entity_kind IN ('film', 'person', 'book', 'play', 'comic', 'series', 'episode', 'game', 'organisation', 'unknown_work')",
        )
