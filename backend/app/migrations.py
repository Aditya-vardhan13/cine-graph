"""Run additive Alembic migrations and safely baseline pre-migration catalogues."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
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


if __name__ == "__main__":
    run_migrations()
