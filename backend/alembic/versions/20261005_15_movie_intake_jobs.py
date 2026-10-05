"""Durable operator-selected film intake queue."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261005_15"
down_revision: Union[str, None] = "20260912_14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movie_intake_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("imdb_id", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("year", sa.Integer()),
        sa.Column("submitted_url", sa.String(length=1000)),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("review_reason", sa.Text()),
        sa.Column("film_entity_id", sa.Uuid(), sa.ForeignKey("canonical_entities.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("imdb_id"),
    )
    op.create_index("ix_movie_intake_jobs_imdb_id", "movie_intake_jobs", ["imdb_id"])
    op.create_index("ix_movie_intake_jobs_status", "movie_intake_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_movie_intake_jobs_status", "movie_intake_jobs")
    op.drop_index("ix_movie_intake_jobs_imdb_id", "movie_intake_jobs")
    op.drop_table("movie_intake_jobs")
