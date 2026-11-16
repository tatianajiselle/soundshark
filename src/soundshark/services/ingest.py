import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from structlog.typing import FilteringBoundLogger

from soundshark.db import (
    ArtistAliasRow,
    ArtistRow,
    CrawlRunRow,
    CreditRow,
    EventRow,
    LineupSlotRow,
    RawPageRow,
    VenueRow,
)
from soundshark.interfaces import PageStore, Source
from soundshark.models import CrawlRun, Event, Page
from soundshark.services.artist_identity import matching_key, split_lineup_slot
from soundshark.utils.slugs import slug_with_short_hash, slugify

log: FilteringBoundLogger = structlog.get_logger()


@dataclass(slots=True)
class IngestSummary:
    pages_read: int = 0
    pages_unparseable: int = 0
    events_written: int = 0
    lineup_slots_written: int = 0
    artists_created: int = 0
    crawl_runs_recorded: int = 0


@dataclass(frozen=True, slots=True)
class PlannedSlot:
    event_source_id: str
    room: str
    position: int
    raw_text: str
    is_b2b: bool
    tags: list[str]
    act_names: list[str]


@dataclass(slots=True)
class PageWithEvents:
    page: Page
    events: list[Event] = field(default_factory=list)


def plan_lineup_slots(event: Event) -> list[PlannedSlot]:
    planned = []
    for room, lineup in event.rooms.items():
        for position, raw_text in enumerate(lineup):
            slot = split_lineup_slot(raw_text)
            planned.append(
                PlannedSlot(
                    event_source_id=event.source_id,
                    room=room,
                    position=position,
                    raw_text=raw_text,
                    is_b2b=slot.is_b2b,
                    tags=slot.tags,
                    act_names=slot.acts,
                )
            )
    return planned


def latest_copy_of_each_event(pages: Iterable[PageWithEvents]) -> dict[str, tuple[Event, Page]]:
    latest: dict[str, tuple[Event, Page]] = {}
    for item in pages:
        for event in item.events:
            seen = latest.get(event.source_id)
            if seen is None or item.page.fetched_at >= seen[1].fetched_at:
                latest[event.source_id] = (event, item.page)
    return latest


def choose_new_artist_slugs(new_keys: Iterable[str], slugs_already_taken: set[str]) -> dict[str, str]:
    taken = set(slugs_already_taken)
    slug_by_key = {}
    for key in new_keys:
        slug = slugify(key)
        if not slug or slug in taken:
            slug = slug_with_short_hash(key)
        taken.add(slug)
        slug_by_key[key] = slug
    return slug_by_key


async def ingest_stored_pages(
    engine: AsyncEngine, source: Source, page_store: PageStore, *, pages_per_batch: int = 100
) -> IngestSummary:
    summary = IngestSummary()
    ingest_log = log.bind(source=source.name)
    ingest_log.info("ingest.started", pages_per_batch=pages_per_batch)
    batch: list[PageWithEvents] = []
    async for page in page_store.iter_pages(source.name):
        summary.pages_read += 1
        try:
            parsed = source.parse(page)
        except Exception:
            summary.pages_unparseable += 1
            ingest_log.exception("ingest.parse_failed", url=page.url)
            continue
        batch.append(PageWithEvents(page, parsed.events))
        if len(batch) >= pages_per_batch:
            await _write_batch(engine, source.name, batch, summary, ingest_log)
            batch = []
    if batch:
        await _write_batch(engine, source.name, batch, summary, ingest_log)

    runs = [run async for run in page_store.iter_runs(source.name)]
    if runs:
        async with engine.begin() as connection:
            await _upsert_crawl_runs(connection, runs)
        summary.crawl_runs_recorded = len(runs)

    ingest_log.info(
        "ingest.finished",
        pages_read=summary.pages_read,
        pages_unparseable=summary.pages_unparseable,
        events_written=summary.events_written,
        lineup_slots_written=summary.lineup_slots_written,
        artists_created=summary.artists_created,
        crawl_runs_recorded=summary.crawl_runs_recorded,
    )
    return summary


async def _write_batch(
    engine: AsyncEngine,
    source_name: str,
    batch: list[PageWithEvents],
    summary: IngestSummary,
    batch_log: FilteringBoundLogger,
) -> None:
    events_by_source_id = latest_copy_of_each_event(batch)
    async with engine.begin() as connection:
        raw_page_ids = await _upsert_raw_pages(connection, source_name, [item.page for item in batch])
        venue_ids = await _upsert_venues(connection, [event for event, _ in events_by_source_id.values()])
        event_ids = await _upsert_events(
            connection, source_name, events_by_source_id, venue_ids, raw_page_ids
        )
        planned_slots = [
            slot for event, _ in events_by_source_id.values() for slot in plan_lineup_slots(event)
        ]
        slot_ids = await _replace_lineup_slots(connection, event_ids, planned_slots)
        artist_ids, artists_created = await _artist_ids_creating_missing(connection, planned_slots)
        await _insert_credits(connection, planned_slots, slot_ids, artist_ids)
    summary.events_written += len(event_ids)
    summary.lineup_slots_written += len(slot_ids)
    summary.artists_created += artists_created
    batch_log.debug(
        "ingest.batch_written",
        pages=len(batch),
        events=len(event_ids),
        lineup_slots=len(slot_ids),
        artists_created=artists_created,
    )


async def _upsert_raw_pages(
    connection: AsyncConnection, source_name: str, pages: list[Page]
) -> dict[str, int]:
    rows = {
        page.url: {
            "source_name": source_name,
            "url": page.url,
            "status": page.status,
            "content_type": page.content_type,
            "content_sha256": hashlib.sha256(page.body).hexdigest(),
            "byte_size": len(page.body),
            "fetched_at": page.fetched_at,
        }
        for page in pages
    }
    updated_columns = ("status", "content_type", "content_sha256", "byte_size", "fetched_at")
    statement = insert(RawPageRow)
    statement = statement.on_conflict_do_update(
        index_elements=["source_name", "url"],
        set_={column: statement.excluded[column] for column in updated_columns},
    ).returning(RawPageRow.url, RawPageRow.id)
    result = await connection.execute(statement, list(rows.values()))
    return {url: page_id for url, page_id in result.all()}


async def _upsert_venues(connection: AsyncConnection, events: list[Event]) -> dict[tuple[str, str], int]:
    venues = sorted({(event.venue, event.city) for event in events})
    if not venues:
        return {}
    statement = insert(VenueRow)
    statement = statement.on_conflict_do_update(
        index_elements=["name", "city"], set_={"name": statement.excluded.name}
    ).returning(VenueRow.name, VenueRow.city, VenueRow.id)
    result = await connection.execute(statement, [{"name": name, "city": city} for name, city in venues])
    return {(name, city): venue_id for name, city, venue_id in result.all()}


async def _upsert_events(
    connection: AsyncConnection,
    source_name: str,
    events_by_source_id: dict[str, tuple[Event, Page]],
    venue_ids: dict[tuple[str, str], int],
    raw_page_ids: dict[str, int],
) -> dict[str, int]:
    if not events_by_source_id:
        return {}
    rows = [
        {
            "source_name": source_name,
            "source_id": event.source_id,
            "venue_id": venue_ids[(event.venue, event.city)],
            "raw_page_id": raw_page_ids.get(page.url),
            "title": event.title,
            "url": event.url,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "ra_id": event.ra_id,
        }
        for event, page in events_by_source_id.values()
    ]
    statement = insert(EventRow)
    updated_columns = ("venue_id", "raw_page_id", "title", "url", "starts_at", "ends_at", "ra_id")
    statement = statement.on_conflict_do_update(
        index_elements=["source_name", "source_id"],
        set_={column: statement.excluded[column] for column in updated_columns}
        | {"last_seen_at": func.now()},
    ).returning(EventRow.source_id, EventRow.id)
    result = await connection.execute(statement, rows)
    return {source_id: event_id for source_id, event_id in result.all()}


async def _replace_lineup_slots(
    connection: AsyncConnection, event_ids: dict[str, int], planned_slots: list[PlannedSlot]
) -> dict[tuple[str, str, int], int]:
    if not event_ids:
        return {}
    await connection.execute(delete(LineupSlotRow).where(LineupSlotRow.event_id.in_(event_ids.values())))
    if not planned_slots:
        return {}
    rows = [
        {
            "event_id": event_ids[slot.event_source_id],
            "room": slot.room,
            "position": slot.position,
            "raw_text": slot.raw_text,
            "is_b2b": slot.is_b2b,
            "tags": slot.tags,
        }
        for slot in planned_slots
    ]
    source_id_by_event_id = {event_id: source_id for source_id, event_id in event_ids.items()}
    result = await connection.execute(
        insert(LineupSlotRow).returning(
            LineupSlotRow.event_id, LineupSlotRow.room, LineupSlotRow.position, LineupSlotRow.id
        ),
        rows,
    )
    return {
        (source_id_by_event_id[event_id], room, position): slot_id
        for event_id, room, position, slot_id in result.all()
    }


async def _artist_ids_creating_missing(
    connection: AsyncConnection, planned_slots: list[PlannedSlot]
) -> tuple[dict[str, int], int]:
    display_name_by_key: dict[str, str] = {}
    for slot in planned_slots:
        for act in slot.act_names:
            display_name_by_key.setdefault(matching_key(act), act)
    if not display_name_by_key:
        return {}, 0

    known = await connection.execute(
        select(ArtistAliasRow.alias_key, ArtistAliasRow.artist_id).where(
            ArtistAliasRow.alias_key.in_(display_name_by_key)
        )
    )
    artist_id_by_key = {key: artist_id for key, artist_id in known.all()}
    new_keys = [key for key in display_name_by_key if key not in artist_id_by_key]
    if not new_keys:
        return artist_id_by_key, 0

    candidate_slugs = {slugify(key) for key in new_keys}
    taken = await connection.execute(select(ArtistRow.slug).where(ArtistRow.slug.in_(candidate_slugs)))
    slug_by_key = choose_new_artist_slugs(new_keys, set(taken.scalars().all()))
    created = await connection.execute(
        insert(ArtistRow).returning(ArtistRow.slug, ArtistRow.id),
        [{"name": display_name_by_key[key], "slug": slug_by_key[key]} for key in new_keys],
    )
    key_by_slug = {slug: key for key, slug in slug_by_key.items()}
    new_artist_ids = {key_by_slug[slug]: artist_id for slug, artist_id in created.all()}
    await connection.execute(
        insert(ArtistAliasRow).on_conflict_do_nothing(index_elements=["alias_key"]),
        [
            {
                "alias_key": key,
                "artist_id": artist_id,
                "display_name": display_name_by_key[key],
                "origin": "auto",
            }
            for key, artist_id in new_artist_ids.items()
        ],
    )
    return artist_id_by_key | new_artist_ids, len(new_artist_ids)


async def _insert_credits(
    connection: AsyncConnection,
    planned_slots: list[PlannedSlot],
    slot_ids: dict[tuple[str, str, int], int],
    artist_ids: dict[str, int],
) -> None:
    credits = {
        (slot_ids[(slot.event_source_id, slot.room, slot.position)], artist_ids[matching_key(act)])
        for slot in planned_slots
        for act in slot.act_names
    }
    if credits:
        await connection.execute(
            insert(CreditRow).on_conflict_do_nothing(),
            [{"lineup_slot_id": slot_id, "artist_id": artist_id} for slot_id, artist_id in sorted(credits)],
        )


async def _upsert_crawl_runs(connection: AsyncConnection, runs: list[CrawlRun]) -> None:
    rows = [
        {
            "id": run.id,
            "source_name": run.source_name,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "pages_fetched": run.pages_fetched,
            "pages_from_store": run.pages_from_store,
            "pages_failed": run.pages_failed,
            "pages_blocked_by_robots": run.pages_blocked_by_robots,
            "events_found": run.events_found,
        }
        for run in runs
    ]
    statement = insert(CrawlRunRow)
    statement = statement.on_conflict_do_update(
        index_elements=["id"],
        set_={column: statement.excluded[column] for column in rows[0] if column != "id"},
    )
    await connection.execute(statement, rows)
