"""Run additive Alembic migrations and safely baseline pre-migration catalogues."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.db import engine

LEGACY_BASELINE_REVISION = "20260812_01"


def alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    return Config(str(backend_root / "alembic.ini"))


def run_migrations() -> None:
    """Upgrade safely; existing pre-Alembic databases are stamped, never reset."""
    config = alembic_config()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "films" in tables and "alembic_version" not in tables:
        command.stamp(config, LEGACY_BASELINE_REVISION)
    command.upgrade(config, "head")


def require_current_schema() -> None:
    """Fail API startup when the explicit migration job has not completed."""
    expected = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != expected:
        raise RuntimeError(
            f"Database schema is at {current or 'unversioned'}, expected {expected}. "
            "Run `python -m app.migrations` before starting the API."
        )


if __name__ == "__main__":
    run_migrations()
