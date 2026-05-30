"""Alembic environment script — runs on every `alembic` CLI command.

Wired to:
- our SQLAlchemy Base from app.core.database (target_metadata = Base.metadata)
- our DATABASE_URL from .env (never duplicated in alembic.ini)
- every ORM model (imported via `app.models` so all tables register with Base.metadata)
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the backend root importable so `from app.* import ...` resolves when alembic
# runs us from the CLI (we're nested two levels deep at migrations/env.py).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# These imports MUST come after sys.path is set up.
from app.core.database import Base, DATABASE_URL  # noqa: E402
from app import models  # noqa: E402, F401 — side effect: registers all ORM models

# Standard Alembic config object — reads alembic.ini.
config = context.config

# Inject our .env-sourced DATABASE_URL. Escape any literal '%' because Alembic's
# ConfigParser treats it as an interpolation marker.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

# Set up Python logging from the [loggers]/[handlers]/[formatters] sections of alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What Alembic compares against the live DB schema to autogenerate migrations.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """'Offline' mode — emit raw SQL without connecting. Rare; used for SQL exports."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """'Online' mode — open a real connection and apply migrations (the normal path)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
