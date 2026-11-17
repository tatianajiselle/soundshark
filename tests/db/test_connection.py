import ssl

import pytest

from soundshark.db import database_url_from_env, sqlalchemy_url
from soundshark.db.connection import asyncpg_ssl_mode, connect_args, ssl_context

NEON_STYLE_URL = (
    "postgresql://user:secret@ep-x.us-west-2.aws.neon.tech/soundshark?sslmode=require&channel_binding=require"
)


def test_neon_url_becomes_an_asyncpg_url_that_verifies_the_server():
    assert (
        sqlalchemy_url(NEON_STYLE_URL)
        == "postgresql+asyncpg://user:secret@ep-x.us-west-2.aws.neon.tech/soundshark?ssl=verify-full"
    )


@pytest.mark.parametrize(
    ("sslmode", "expected"),
    [
        ("require", "verify-full"),
        ("verify-full", "verify-full"),
        ("verify-ca", "verify-ca"),
        ("prefer", "prefer"),
        ("allow", "allow"),
        ("disable", "disable"),
    ],
)
def test_ssl_modes_map_to_asyncpg(sslmode, expected):
    url = f"postgresql://u:p@db.example/db?sslmode={sslmode}"
    assert asyncpg_ssl_mode(url) == expected
    assert sqlalchemy_url(url) == f"postgresql+asyncpg://u:p@db.example/db?ssl={expected}"


def test_url_without_query_stays_plain():
    assert sqlalchemy_url("postgres://u:p@localhost:5432/db") == "postgresql+asyncpg://u:p@localhost:5432/db"
    assert connect_args("postgres://u:p@localhost:5432/db") == {}


def test_other_query_params_are_kept():
    url = "postgresql://u:p@db.example/db?application_name=crawler&sslmode=require"
    assert (
        sqlalchemy_url(url)
        == "postgresql+asyncpg://u:p@db.example/db?application_name=crawler&ssl=verify-full"
    )


def test_require_checks_the_certificate_and_the_hostname():
    context = connect_args(NEON_STYLE_URL)["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


def test_verify_ca_checks_the_certificate_but_not_the_hostname():
    context = ssl_context("verify-ca")
    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert not context.check_hostname


@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer"])
def test_local_modes_get_no_verifying_context(sslmode):
    assert connect_args(f"postgresql://u:p@localhost/db?sslmode={sslmode}") == {}


def test_missing_database_url_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        database_url_from_env()
