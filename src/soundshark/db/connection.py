import os
import ssl
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_QUERY_PARAMS_ASYNCPG_DOES_NOT_ACCEPT = frozenset({"sslmode", "channel_binding"})
_SSL_MODE_UPGRADES = {"require": "verify-full"}
_VERIFYING_SSL_MODES = frozenset({"verify-ca", "verify-full"})


def asyncpg_ssl_mode(postgres_url: str) -> str | None:
    ssl_mode = dict(parse_qsl(urlsplit(postgres_url).query)).get("sslmode")
    if not ssl_mode:
        return None
    return _SSL_MODE_UPGRADES.get(ssl_mode, ssl_mode)


def sqlalchemy_url(postgres_url: str) -> str:
    parts = urlsplit(postgres_url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query)
        if key not in _QUERY_PARAMS_ASYNCPG_DOES_NOT_ACCEPT
    ]
    ssl_mode = asyncpg_ssl_mode(postgres_url)
    if ssl_mode:
        kept.append(("ssl", ssl_mode))
    return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, urlencode(kept), ""))


def ssl_context(ssl_mode: str | None) -> ssl.SSLContext | None:
    if ssl_mode not in _VERIFYING_SSL_MODES:
        return None
    context = ssl.create_default_context()
    context.check_hostname = ssl_mode == "verify-full"
    return context


def connect_args(postgres_url: str) -> dict[str, Any]:
    context = ssl_context(asyncpg_ssl_mode(postgres_url))
    return {"ssl": context} if context else {}


def database_url_from_env(variable: str = "DATABASE_URL") -> str:
    url = os.environ.get(variable)
    if not url:
        raise RuntimeError(f"{variable} is not set; add it to .env (see .env.example)")
    return url


MIGRATIONS_URL_ENV_VAR = "MIGRATIONS_DATABASE_URL"


def migrations_database_url() -> str:
    return os.environ.get(MIGRATIONS_URL_ENV_VAR) or database_url_from_env()


def create_database_engine(postgres_url: str) -> AsyncEngine:
    return create_async_engine(
        sqlalchemy_url(postgres_url), pool_pre_ping=True, connect_args=connect_args(postgres_url)
    )
