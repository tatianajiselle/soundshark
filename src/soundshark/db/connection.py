import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_QUERY_PARAMS_ASYNCPG_DOES_NOT_ACCEPT = frozenset({"sslmode", "channel_binding"})


def sqlalchemy_url(postgres_url: str) -> str:
    parts = urlsplit(postgres_url)
    query = parse_qsl(parts.query)
    kept = [(key, value) for key, value in query if key not in _QUERY_PARAMS_ASYNCPG_DOES_NOT_ACCEPT]
    ssl_mode = dict(query).get("sslmode")
    if ssl_mode:
        kept.append(("ssl", ssl_mode))
    return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, urlencode(kept), ""))


def database_url_from_env(variable: str = "DATABASE_URL") -> str:
    url = os.environ.get(variable)
    if not url:
        raise RuntimeError(f"{variable} is not set; add it to .env (see .env.example)")
    return url


MIGRATIONS_URL_ENV_VAR = "MIGRATIONS_DATABASE_URL"


def migrations_database_url() -> str:
    return os.environ.get(MIGRATIONS_URL_ENV_VAR) or database_url_from_env()


def create_database_engine(postgres_url: str) -> AsyncEngine:
    return create_async_engine(sqlalchemy_url(postgres_url), pool_pre_ping=True)
