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
from soundshark.services.credits import build_credits
from soundshark.services.ingest import ingest_stored_pages
from soundshark.sources import DemoSource
from tests.fakes import InMemoryPageStore

load_dotenv()
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
MARCH_URL = "https://demo.soundshark.test/2026-03/"

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


async def ingest_and_identify(engine: AsyncEngine, store: InMemoryPageStore) -> None:
    await ingest_stored_pages(engine, DemoSource(), store)
    await build_credits(engine)


async def change_march_lineup(store: InMemoryPageStore, old_name: str, new_name: str) -> None:
    march = await store.load_page("demo", MARCH_URL)
    assert march is not None
    changed = replace(
        march,
        body=march.text.replace(old_name, new_name).encode(),
        fetched_at=march.fetched_at + timedelta(days=1),
    )
    await store.save_page("demo", changed)


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
        counts = {}
        for table in tables:
            count = await connection.execute(select(func.count()).select_from(table))
            counts[table.__tablename__] = count.scalar_one()
        return counts


async def fetch_all(engine: AsyncEngine, statement) -> list:
    async with engine.connect() as connection:
        return list((await connection.execute(statement)).all())


async def test_migrations_create_every_table_and_search_extensions(engine):
    async with engine.connect() as connection:
        version = (await connection.execute(text("select version_num from alembic_version"))).scalar_one()
        extensions = (await connection.execute(text("select extname from pg_extension"))).scalars().all()
    assert version == "0001"
    assert {"unaccent", "pg_trgm"} <= set(extensions)
    assert set(await count_rows(engine)) == {table.name for table in TableBase.metadata.sorted_tables}


async def test_ingest_writes_only_source_facts_and_provenance(engine):
    summary = await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    assert summary.pages_parsed == 3
    assert summary.events_written == 4
    assert await count_rows(engine) == {
        "crawl_runs": 1,
        "raw_pages": 3,
        "venues": 2,
        "events": 4,
        "lineup_slots": 14,
        "artists": 0,
        "artist_aliases": 0,
        "credits": 0,
    }


async def test_identify_creates_artists_aliases_and_credits(engine):
    await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    summary = await build_credits(engine)
    assert summary.artists_created == 8
    counts = await count_rows(engine)
    assert (counts["artists"], counts["artist_aliases"], counts["credits"]) == (8, 8, 15)


async def test_every_event_traces_back_to_a_page_version_and_a_crawl(engine):
    store = await demo_page_store()
    [crawl_run] = store.saved_runs
    await ingest_stored_pages(engine, DemoSource(), store)
    rows = await fetch_all(
        engine,
        select(EventRow.source_id, RawPageRow.url, RawPageRow.storage_path, CrawlRunRow.id)
        .join(RawPageRow, RawPageRow.id == EventRow.raw_page_id)
        .join(CrawlRunRow, CrawlRunRow.id == RawPageRow.crawl_run_id),
    )
    assert len(rows) == 4
    assert all(run_id == crawl_run.id and storage_path for _, _, storage_path, run_id in rows)


async def test_venues_get_their_timezone(engine):
    await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    timezones = {tz for (tz,) in await fetch_all(engine, select(VenueRow.timezone))}
    assert timezones == {"Europe/Berlin"}


async def test_event_times_keep_their_time_zone(engine):
    await ingest_stored_pages(engine, DemoSource(), await demo_page_store())
    [(starts_at,)] = await fetch_all(engine, select(EventRow.starts_at).where(EventRow.source_id == "d1"))
    assert starts_at.utcoffset() is not None
    assert starts_at.isoformat().startswith("2026-03-06T22:00:00")


async def test_running_everything_twice_changes_nothing(engine):
    store = await demo_page_store()
    await ingest_and_identify(engine, store)
    first_counts = await count_rows(engine)
    first_events = sorted(await fetch_all(engine, select(EventRow.source_id, EventRow.id)))
    first_credits = sorted(await fetch_all(engine, select(CreditRow.lineup_slot_id, CreditRow.artist_id)))

    second_ingest = await ingest_stored_pages(engine, DemoSource(), store)
    second_identify = await build_credits(engine)
    assert second_ingest.events_with_new_lineups == 0
    assert second_identify.artists_created == 0
    assert second_identify.credits_written == 0
    assert await count_rows(engine) == first_counts
    assert sorted(await fetch_all(engine, select(EventRow.source_id, EventRow.id))) == first_events
    assert (
        sorted(await fetch_all(engine, select(CreditRow.lineup_slot_id, CreditRow.artist_id)))
        == first_credits
    )


async def test_b2b_slot_credits_both_artists(engine):
    await ingest_and_identify(engine, await demo_page_store())
    credited = await fetch_all(
        engine,
        select(ArtistRow.name, LineupSlotRow.is_b2b)
        .join(CreditRow, CreditRow.artist_id == ArtistRow.id)
        .join(LineupSlotRow, LineupSlotRow.id == CreditRow.lineup_slot_id)
        .where(LineupSlotRow.raw_text == "Ora Vance b2b Juno Hale"),
    )
    assert sorted(credited) == [("Juno Hale", True), ("Ora Vance", True)]


async def test_changed_page_keeps_both_versions_and_replaces_the_lineup(engine):
    store = await demo_page_store()
    await ingest_and_identify(engine, store)
    await change_march_lineup(store, "Tamsin Rook", "Nova Quist")
    summary = await ingest_stored_pages(engine, DemoSource(), store)
    assert summary.events_with_new_lineups == 1

    march_versions = await fetch_all(
        engine,
        select(RawPageRow.is_latest).where(RawPageRow.url == MARCH_URL).order_by(RawPageRow.fetched_at),
    )
    assert [is_latest for (is_latest,) in march_versions] == [False, True]
    [(points_at_latest,)] = await fetch_all(
        engine,
        select(RawPageRow.is_latest)
        .join(EventRow, EventRow.raw_page_id == RawPageRow.id)
        .where(EventRow.source_id == "d1"),
    )
    assert points_at_latest

    d1_main = await fetch_all(
        engine,
        select(LineupSlotRow.raw_text)
        .join(EventRow, EventRow.id == LineupSlotRow.event_id)
        .where(EventRow.source_id == "d1", LineupSlotRow.room == "Main")
        .order_by(LineupSlotRow.position),
    )
    assert [raw for (raw,) in d1_main] == ["Ora Vance", "Mirek Sol", "Nova Quist"]

    await build_credits(engine)
    nova = await fetch_all(
        engine,
        select(ArtistRow.name)
        .join(CreditRow, CreditRow.artist_id == ArtistRow.id)
        .where(ArtistRow.name == "Nova Quist"),
    )
    assert nova == [("Nova Quist",)]


async def test_manual_alias_wins_and_survives_a_rebuild(engine):
    async with engine.begin() as connection:
        chosen_artist = (
            await connection.execute(
                insert(ArtistRow).values(name="Juno Hale", slug="juno", kind="person").returning(ArtistRow.id)
            )
        ).scalar_one()
        await connection.execute(
            insert(ArtistAliasRow).values(
                alias_key="juno hale", artist_id=chosen_artist, display_name="Juno Hale", origin="manual"
            )
        )

    async def juno_credits() -> int:
        [(count,)] = await fetch_all(engine, select(func.count()).where(CreditRow.artist_id == chosen_artist))
        return count

    await ingest_and_identify(engine, await demo_page_store())
    assert await juno_credits() == 2

    rebuild = await build_credits(engine, rebuild=True)
    assert rebuild.automatic_aliases_removed == 7
    assert rebuild.artists_removed == 7
    assert await juno_credits() == 2
    [(origin, artist_id)] = await fetch_all(
        engine,
        select(ArtistAliasRow.origin, ArtistAliasRow.artist_id).where(
            ArtistAliasRow.alias_key == "juno hale"
        ),
    )
    assert (origin, artist_id) == ("manual", chosen_artist)
    counts = await count_rows(engine)
    assert (counts["artists"], counts["credits"]) == (8, 15)


async def test_artist_kind_defaults_to_unknown(engine):
    await ingest_and_identify(engine, await demo_page_store())
    assert {kind for (kind,) in await fetch_all(engine, select(ArtistRow.kind))} == {"unknown"}
