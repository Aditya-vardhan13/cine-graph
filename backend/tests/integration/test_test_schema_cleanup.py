"""Verify cleanup affects only schemas created by this test process."""
from sqlalchemy import text

from tests.postgres_test_db import cleanup_created_test_schemas, isolated_postgres_engine


def test_created_test_schema_is_removed_without_dropping_public():
    engine = isolated_postgres_engine()
    with engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        connection.execute(text("CREATE TABLE cleanup_fixture (id integer)"))
        assert connection.scalar(text("SELECT to_regnamespace(:schema) IS NOT NULL"), {"schema": schema})
    cleanup_created_test_schemas()
    # A new helper creates a different isolated schema; it will be cleaned by
    # the outer test fixture after this assertion.
    check_engine = isolated_postgres_engine()
    with check_engine.connect() as connection:
        assert not connection.scalar(text("SELECT to_regnamespace(:schema) IS NOT NULL"), {"schema": schema})
        assert connection.scalar(text("SELECT to_regnamespace('public') IS NOT NULL"))
