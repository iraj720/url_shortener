"""
Alembic Environment Configuration

This file configures Alembic to work with our async SQLModel/SQLAlchemy setup.
It handles:
- Database connection from settings
- Model imports for autogenerate
- Sync engine creation for migrations (Alembic uses sync drivers)
"""

from logging.config import fileConfig
from sqlalchemy import pool, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import settings and models
from app.core.setting import settings
from sqlmodel import SQLModel
from app.db import models  # Import all models so Alembic can detect them

# this is the Alembic Config object
config = context.config

# Override sqlalchemy.url with our settings
# Convert async URLs to sync URLs for Alembic (Alembic uses sync driver)
database_url = settings.DATABASE_URL

# Determine if we're using SQLite
is_sqlite = database_url.startswith("sqlite+aiosqlite://") or database_url.startswith("sqlite://")

# Convert async database URLs to sync URLs for Alembic
if database_url.startswith("sqlite+aiosqlite://"):
    # SQLite: Remove aiosqlite, use sqlite
    # Handle different path formats:
    # - sqlite+aiosqlite:///absolute/path -> sqlite:///absolute/path (three slashes)
    # - sqlite+aiosqlite://./relative/path -> sqlite:///./relative/path (three slashes + dot)
    if database_url.startswith("sqlite+aiosqlite:///"):
        # Absolute path (three slashes after protocol)
        database_url = database_url.replace("sqlite+aiosqlite:///", "sqlite:///")
    elif database_url.startswith("sqlite+aiosqlite://./"):
        # Relative path starting with ./
        database_url = database_url.replace("sqlite+aiosqlite://", "sqlite:///")
    else:
        # Other relative path formats
        database_url = database_url.replace("sqlite+aiosqlite://", "sqlite:///")
elif database_url.startswith("postgresql+asyncpg://"):
    # PostgreSQL: Convert asyncpg to psycopg2 (sync driver)
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get SQLModel metadata for autogenerate
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # For SQLite, use sync engine (simpler and more reliable)
    # For PostgreSQL, we could use async, but sync works fine for migrations
    if is_sqlite:
        # SQLite: Use sync engine
        connectable = create_engine(
            database_url,
            poolclass=pool.NullPool,
        )
        
        with connectable.connect() as connection:
            do_run_migrations(connection)
        
        connectable.dispose()
    else:
        # PostgreSQL: Use async engine
        async def run_async_migrations() -> None:
            connectable = async_engine_from_config(
                config.get_section(config.config_ini_section, {}),
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
            )

            async with connectable.connect() as connection:
                await connection.run_sync(do_run_migrations)

            await connectable.dispose()
        
        import asyncio
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

