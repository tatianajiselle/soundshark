import re
import secrets
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

DEFAULT_JOBS_ROLE = "soundshark_jobs"
MIGRATIONS_TABLE = "alembic_version"
TABLE_PRIVILEGES = "select, insert, update, delete"
SEQUENCE_PRIVILEGES = "usage, select"
_ROLE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def check_role_name(role: str) -> str:
    if not _ROLE_NAME.fullmatch(role):
        raise ValueError(f"role name {role!r} must be lowercase letters, digits and underscores")
    return role


def new_password() -> str:
    return secrets.token_urlsafe(32)


def url_for_role(owner_url: str, role: str, password: str) -> str:
    parts = urlsplit(owner_url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    credentials = f"{quote(role, safe='')}:{quote(password, safe='')}"
    return urlunsplit((parts.scheme, f"{credentials}@{host}", parts.path, parts.query, ""))


def jobs_role_grants(role: str, database: str, owner: str) -> list[str]:
    default_privileges = f"alter default privileges for role {owner} in schema public grant"
    return [
        f"grant connect on database {database} to {role}",
        f"grant usage on schema public to {role}",
        f"grant {TABLE_PRIVILEGES} on all tables in schema public to {role}",
        f"grant {SEQUENCE_PRIVILEGES} on all sequences in schema public to {role}",
        f"{default_privileges} {TABLE_PRIVILEGES} on tables to {role}",
        f"{default_privileges} {SEQUENCE_PRIVILEGES} on sequences to {role}",
    ]


async def create_or_rotate_jobs_role(owner_engine: AsyncEngine, role: str) -> str:
    check_role_name(role)
    password = new_password()
    async with owner_engine.begin() as connection:
        quote_identifier = connection.dialect.identifier_preparer.quote
        database, owner = (await connection.execute(text("select current_database(), current_user"))).one()
        role_exists = (
            await connection.execute(text("select 1 from pg_roles where rolname = :role"), {"role": role})
        ).scalar() is not None
        verb = "alter" if role_exists else "create"
        await connection.execute(
            text(f"{verb} role {quote_identifier(role)} with login password '{password}'")
        )
        for statement in jobs_role_grants(
            quote_identifier(role), quote_identifier(database), quote_identifier(owner)
        ):
            await connection.execute(text(statement))
        migrations_table = (
            await connection.execute(
                text("select to_regclass(:table)"), {"table": f"public.{MIGRATIONS_TABLE}"}
            )
        ).scalar()
        if migrations_table is not None:
            await connection.execute(
                text(f"revoke insert, update, delete on {MIGRATIONS_TABLE} from {quote_identifier(role)}")
            )
    return password


def write_env_value(env_file: Path, key: str, value: str) -> None:
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    entry = f"{key}={value}"
    kept: list[str] = []
    written = False
    for line in lines:
        if line.partition("=")[0].strip() == key:
            if not written:
                kept.append(entry)
                written = True
            continue
        kept.append(line)
    if not written:
        kept.append(entry)
    env_file.touch(mode=0o600, exist_ok=True)
    env_file.chmod(0o600)
    env_file.write_text("\n".join(kept) + "\n")
