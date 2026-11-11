import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db import Base

# Import every model module so all tables register on Base.metadata (needed for
# autogenerate and for a complete target_metadata). Add new model modules here;
# tests/test_migration_safety.py fails if one is missing.
from app.models import (  # noqa: F401
    bill,
    committee,
    contribution,
    crosswalk,
    finance,
    member,
    pipeline_status,
    source_run,
    upstream_budget,
    vote,
    zip_district,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations run on every backend start while the previous container may
# still be serving. A DDL statement queued behind a long-held lock would block
# every later query on that table, so give up quickly instead; the container
# exits non-zero, the deploy fails its health check and the old one stays up.
LOCK_TIMEOUT = "5s"

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    # The URL is read from settings directly, never round-tripped through
    # alembic's ConfigParser, where a percent-encoded password would be
    # misread as interpolation syntax.
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"lock_timeout": LOCK_TIMEOUT}},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
