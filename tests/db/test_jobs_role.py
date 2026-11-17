import secrets
import stat

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError

from soundshark.db import VenueRow, create_database_engine
from soundshark.db.roles import (
    check_role_name,
    create_or_rotate_jobs_role,
    jobs_role_grants,
    url_for_role,
    write_env_value,
)
from tests.db.conftest import TEST_DATABASE_URL

OWNER_URL = "postgresql://owner:owner-secret@ep-x.aws.neon.tech:5432/soundshark?sslmode=require"


def test_url_for_role_swaps_only_the_credentials():
    assert url_for_role(OWNER_URL, "jobs", "p-w_d") == (
        "postgresql://jobs:p-w_d@ep-x.aws.neon.tech:5432/soundshark?sslmode=require"
    )


def test_url_for_role_without_a_port():
    url = url_for_role("postgresql://o:s@host/db", "jobs", "pw")
    assert url == "postgresql://jobs:pw@host/db"


@pytest.mark.parametrize("bad_name", ["Jobs", "1jobs", "jobs;drop", "", "x" * 64])
def test_role_names_are_plain_identifiers(bad_name):
    with pytest.raises(ValueError, match="role name"):
        check_role_name(bad_name)


def test_grants_never_include_schema_changes():
    statements = " ".join(jobs_role_grants("jobs", "db", "owner"))
    for forbidden in ("create on", "all privileges", "truncate", "references", "trigger", "superuser"):
        assert forbidden not in statements


def test_write_env_value_replaces_the_key_and_keeps_the_rest(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nDATABASE_URL=old\nB=2\nDATABASE_URL=older\n")
    write_env_value(env_file, "DATABASE_URL", "new")
    assert env_file.read_text() == "A=1\nDATABASE_URL=new\nB=2\n"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_write_env_value_appends_to_a_new_file(tmp_path):
    env_file = tmp_path / ".env"
    write_env_value(env_file, "DATABASE_URL", "new")
    assert env_file.read_text() == "DATABASE_URL=new\n"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


TEST_ROLE_PREFIX = "soundshark_test_jobs_"


async def drop_role(engine, role):
    async with engine.begin() as connection:
        database, owner = (await connection.execute(text("select current_database(), current_user"))).one()
        default_privileges = f'alter default privileges for role "{owner}" in schema public revoke all'
        for statement in (
            f"revoke all on all tables in schema public from {role}",
            f"revoke all on all sequences in schema public from {role}",
            f"revoke all on schema public from {role}",
            f"{default_privileges} on tables from {role}",
            f"{default_privileges} on sequences from {role}",
            f'revoke all on database "{database}" from {role}',
            f"drop role {role}",
        ):
            await connection.execute(text(statement))


@pytest.fixture
async def jobs_role(engine):
    async with engine.connect() as connection:
        leftovers = (
            (
                await connection.execute(
                    text("select rolname from pg_roles where starts_with(rolname, :prefix)"),
                    {"prefix": TEST_ROLE_PREFIX},
                )
            )
            .scalars()
            .all()
        )
    for leftover in leftovers:
        await drop_role(engine, leftover)
    role = f"{TEST_ROLE_PREFIX}{secrets.token_hex(4)}"
    password = await create_or_rotate_jobs_role(engine, role)
    yield role, password
    await drop_role(engine, role)


async def test_the_jobs_role_reads_and_writes_rows(jobs_role):
    role, password = jobs_role
    jobs_engine = create_database_engine(url_for_role(TEST_DATABASE_URL, role, password))
    try:
        async with jobs_engine.begin() as connection:
            await connection.execute(insert(VenueRow).values(name="Harbour Hall", city="Testville"))
            names = (await connection.execute(select(VenueRow.name))).scalars().all()
            await connection.execute(text("update venues set city = 'Elsewhere'"))
            await connection.execute(text("delete from venues"))
        assert names == ["Harbour Hall"]
    finally:
        await jobs_engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "create table sneaky (id int)",
        "drop table artists",
        "alter table artists add column sneaky int",
        "truncate artists",
        "delete from alembic_version",
        "update alembic_version set version_num = 'x'",
        "create role sneaky_role",
    ],
)
async def test_the_jobs_role_cannot_change_the_schema(jobs_role, statement):
    role, password = jobs_role
    jobs_engine = create_database_engine(url_for_role(TEST_DATABASE_URL, role, password))
    try:
        with pytest.raises(DBAPIError, match="permission denied|must be owner"):
            async with jobs_engine.begin() as connection:
                await connection.execute(text(statement))
    finally:
        await jobs_engine.dispose()


async def test_rotating_the_password_locks_out_the_old_one(engine, jobs_role):
    role, old_password = jobs_role
    new_password = await create_or_rotate_jobs_role(engine, role)
    assert new_password != old_password
    old_engine = create_database_engine(url_for_role(TEST_DATABASE_URL, role, old_password))
    try:
        with pytest.raises(DBAPIError, match="password authentication failed"):
            async with old_engine.connect() as connection:
                await connection.execute(text("select 1"))
    finally:
        await old_engine.dispose()
