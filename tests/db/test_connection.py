import pytest

from soundshark.db import database_url_from_env, sqlalchemy_url


def test_neon_url_becomes_an_asyncpg_url_with_ssl():
    neon_url = "postgresql://user:secret@ep-x.us-west-2.aws.neon.tech/soundshark?sslmode=require&channel_binding=require"
    assert (
        sqlalchemy_url(neon_url)
        == "postgresql+asyncpg://user:secret@ep-x.us-west-2.aws.neon.tech/soundshark?ssl=require"
    )


def test_url_without_query_stays_plain():
    assert sqlalchemy_url("postgres://u:p@localhost:5432/db") == "postgresql+asyncpg://u:p@localhost:5432/db"


def test_missing_database_url_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        database_url_from_env()
