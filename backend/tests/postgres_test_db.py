"""Isolated PostgreSQL schemas for persistence-level tests.

These tests intentionally do not use SQLite: PostgreSQL constraints, UUIDs,
JSON behaviour and extensions are part of CineGraph's real contract.  Each
caller receives a fresh schema inside the dedicated ``cinegraph_test``
database, so it cannot touch the working corpus or the API fixture in
``public``.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine


DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/cinegraph_test"


def isolated_postgres_engine() -> Engine:
    if os.environ.get("CINEGRAPH_RUN_INTEGRATION") != "1":
        pytest.skip("persistence tests run only against the isolated local PostgreSQL integration database")
    database_url = os.environ.get("CINEGRAPH_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    admin = create_engine(database_url)
    database_name = admin.url.database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError(f"Refusing to create a test schema outside a *_test database: {database_name!r}")
    schema = f"persistence_{uuid4().hex}"
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def set_test_schema(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f'SET search_path TO "{schema}"')
        finally:
            cursor.close()

    return engine
