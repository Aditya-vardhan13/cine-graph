"""Add PostgreSQL indexes for the catalogue's interactive read paths."""
from typing import Sequence, Union

from alembic import op


revision: str = "20260816_11"
down_revision: Union[str, None] = "20260816_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `%ILIKE%` is the existing live-title-search contract. pg_trgm lets
    # PostgreSQL execute that contract through a GIN index instead of a
    # catalogue-wide scan as the English collection grows.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_films_canonical_title_trgm "
        "ON films USING gin (canonical_title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_films_published_release_title "
        "ON films (review_status, release_date DESC, canonical_title)"
    )
    op.create_index("ix_film_genres_genre_id", "film_genres", ["genre_id"])


def downgrade() -> None:
    op.drop_index("ix_film_genres_genre_id", table_name="film_genres")
    op.execute("DROP INDEX IF EXISTS ix_films_published_release_title")
    op.execute("DROP INDEX IF EXISTS ix_films_canonical_title_trgm")
    # `pg_trgm` may be shared by a user's own database features, so it is not
    # dropped automatically during downgrade.
