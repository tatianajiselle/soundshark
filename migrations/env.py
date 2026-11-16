import asyncio

from alembic import context
from dotenv import find_dotenv, load_dotenv
from sqlalchemy.engine import Connection

from soundshark.db import TableBase, create_database_engine, database_url_from_env, sqlalchemy_url

load_dotenv(find_dotenv(usecwd=True))


def _database_url() -> str:
    return context.config.attributes.get("database_url") or database_url_from_env()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=TableBase.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_online() -> None:
    engine = create_database_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def _run_migrations_offline() -> None:
    context.configure(
        url=sqlalchemy_url(_database_url()),
        target_metadata=TableBase.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    _run_migrations_offline()
else:
    asyncio.run(_run_migrations_online())
