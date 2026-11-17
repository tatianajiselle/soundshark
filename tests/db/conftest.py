import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import text

from soundshark.db import TableBase, create_database_engine

load_dotenv()
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def pytest_collection_modifyitems(items):
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL is not set")
    for item in items:
        if {"engine", "migrated_test_database"} & set(getattr(item, "fixturenames", ())):
            item.add_marker(skip)


def run_alembic(step: str, target: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = TEST_DATABASE_URL
    getattr(command, step)(config, target)


async def _empty_the_test_database() -> None:
    engine = create_database_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("drop schema public cascade"))
        await connection.execute(text("create schema public"))
    await engine.dispose()


@pytest.fixture(scope="session")
def migrated_test_database():
    asyncio.run(_empty_the_test_database())
    run_alembic("upgrade", "head")
    run_alembic("downgrade", "base")
    run_alembic("upgrade", "head")


@pytest.fixture
async def engine(migrated_test_database):
    engine = create_database_engine(TEST_DATABASE_URL)
    table_names = ", ".join(table.name for table in TableBase.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"truncate {table_names} restart identity cascade"))
    yield engine
    await engine.dispose()
