import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from soundshark.db import (
    ArtistAliasRow,
    ArtistRow,
    CrawlRunRow,
    CreditRow,
    EventRow,
    LineupSlotRow,
    RawPageRow,
    TableBase,
    VenueRow,
    create_database_engine,
)
from soundshark.services import crawl
from soundshark.services.ingest import ingest_stored_pages
from soundshark.sources import DemoSource
from tests.fakes import InMemoryPageStore

load_dotenv()
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


def run_alembic(step: str, target: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = TEST_DATABASE_URL
    getattr(command, step)(config, target)


@pytest.fixture(scope="session")
def migrated_test_database():
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


async def demo_page_store() -> InMemoryPageStore:
    source = DemoSource(seconds_between_requests=0)
    store = InMemoryPageStore()
    async with httpx.AsyncClient(transport=source.http_transport) as http_client:
        await crawl(source, http_client, page_store=store)
    return store


async def count_rows(engine: AsyncEngine) -> dict[str, int]:
    tables = [
        CrawlRunRow,
        RawPageRow,
        VenueRow,
        EventRow,
        LineupSlotRow,
        ArtistRow,
        ArtistAliasRow,
        CreditRow,
    ]
    async with engine.connect() as connection:
        return {
            table.__tablename__: (
                await connection.execute(select(func.count()).select_from(table))
            ).scalar_one()
            for table in tables
        }


async def test_migrations_create_every_table(engine):
    async with engine.connect() as connection:
        version = (await connection.execute(text("select version_num from alembic_version"))).scalar_one()
    assert version == "0001"
    assert set(await count_rows(engine)) == {table.name for table in TableBase.metadata.sorted_tables}


async def test_ingest_writes_every_layer(engine):
    summary = await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    assert summary.pages_read == 3
    assert summary.events_written == 4
    assert await count_rows(engine) == {
        "crawl_runs": 1,
        "raw_pages": 3,
        "venues": 2,
        "events": 4,
        "lineup_slots": 14,
        "artists": 8,
        "artist_aliases": 8,
        "credits": 15,
    }


async def test_ingest_twice_gives_the_same_database(engine):
    store = await demo_page_store()
    await ingest_stored_pages(engine, DemoSource(), store)
    first_counts = await count_rows(engine)
    async with engine.connect() as connection:
        first_ids = (await connection.execute(select(EventRow.source_id, EventRow.id))).all()
        first_artists = (await connection.execute(select(ArtistRow.slug, ArtistRow.id))).all()

    second = await ingest_stored_pages(engine, DemoSource(), store)
    assert second.artists_created == 0
    assert await count_rows(engine) == first_counts
    async with engine.connect() as connection:
        assert sorted((await connection.execute(select(EventRow.source_id, EventRow.id))).all()) == sorted(
            first_ids
        )
        assert sorted((await connection.execute(select(ArtistRow.slug, ArtistRow.id))).all()) == sorted(
            first_artists
        )


async def test_event_times_keep_their_time_zone(engine):
    await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    async with engine.connect() as connection:
        starts_at = (
            await connection.execute(select(EventRow.starts_at).where(EventRow.source_id == "d1"))
        ).scalar_one()
    assert starts_at.utcoffset() is not None
    assert starts_at.isoformat().startswith("2026-03-06T22:00:00")


async def test_b2b_slot_credits_both_artists(engine):
    await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    async with engine.connect() as connection:
        credited = (
            await connection.execute(
                select(ArtistRow.name)
                .join(CreditRow, CreditRow.artist_id == ArtistRow.id)
                .join(LineupSlotRow, LineupSlotRow.id == CreditRow.lineup_slot_id)
                .where(LineupSlotRow.raw_text == "Ora Vance b2b Juno Hale")
            )
        ).scalars()
        is_b2b = (
            await connection.execute(
                select(LineupSlotRow.is_b2b).where(LineupSlotRow.raw_text == "Ora Vance b2b Juno Hale")
            )
        ).scalar_one()
    assert sorted(credited) == ["Juno Hale", "Ora Vance"]
    assert is_b2b


async def test_manual_alias_decisions_win(engine):
    async with engine.begin() as connection:
        chosen_artist = (
            await connection.execute(
                insert(ArtistRow).values(name="Juno Hale", slug="juno").returning(ArtistRow.id)
            )
        ).scalar_one()
        await connection.execute(
            insert(ArtistAliasRow).values(
                alias_key="juno hale", artist_id=chosen_artist, display_name="Juno Hale", origin="manual"
            )
        )
    await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    async with engine.connect() as connection:
        alias = (
            await connection.execute(select(ArtistAliasRow).where(ArtistAliasRow.alias_key == "juno hale"))
        ).one()
        juno_credits = (
            await connection.execute(select(func.count()).where(CreditRow.artist_id == chosen_artist))
        ).scalar_one()
    assert alias.origin == "manual"
    assert alias.artist_id == chosen_artist
    assert juno_credits == 2


async def test_changed_lineup_replaces_the_event_slots(engine):
    store = await demo_page_store()
    await ingest_stored_pages(engine, DemoSource(), store)

    march_url = "https://demo.soundshark.test/2026-03/"
    march = store.pages[("demo", march_url)]
    changed_body = march.text.replace("Tamsin Rook", "Nova Quist").encode()
    store.pages[("demo", march_url)] = replace(
        march, body=changed_body, fetched_at=march.fetched_at + timedelta(days=1)
    )
    await ingest_stored_pages(engine, DemoSource(), store)

    async with engine.connect() as connection:
        d1_slots = (
            await connection.execute(
                select(LineupSlotRow.raw_text)
                .join(EventRow, EventRow.id == LineupSlotRow.event_id)
                .where(EventRow.source_id == "d1", LineupSlotRow.room == "Main")
                .order_by(LineupSlotRow.position)
            )
        ).scalars()
        assert list(d1_slots) == ["Ora Vance", "Mirek Sol", "Nova Quist"]
    assert (await count_rows(engine))["lineup_slots"] == 14
