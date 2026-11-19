from collections.abc import Iterable
from dataclasses import dataclass, field

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from structlog.typing import FilteringBoundLogger

from soundshark.db import CrawlRunRow, EventRow, LineupSlotRow, RawPageRow, VenueRow
from soundshark.db.bulk import is_any_of
from soundshark.interfaces import PageStore, Source
from soundshark.models import CrawlRun, Event, Page, StoredPageVersion
from soundshark.services.artist_identity import split_lineup_slot

log: FilteringBoundLogger = structlog.get_logger()

PageVersionKey = tuple[str, str]
SlotContent = tuple[str, int, str, bool, tuple[str, ...]]


@dataclass(slots=True)
class IngestSummary:
    page_versions_read: int = 0
    pages_parsed: int = 0
    pages_unparseable: int = 0
    events_written: int = 0
    events_with_new_lineups: int = 0
    lineup_slots_written: int = 0
    crawl_runs_recorded: int = 0


@dataclass(frozen=True, slots=True)
class PlannedSlot:
    event_source_id: str
    room: str
    position: int
    raw_text: str
    is_b2b: bool
    tags: list[str]


@dataclass(slots=True)
class PageWithEvents:
    page: Page
    events: list[Event] = field(default_factory=list)


def version_key(page: Page) -> PageVersionKey:
    return (page.url, page.content_sha256)


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


async def ingest_stored_pages(
    engine: AsyncEngine, source: Source, page_store: PageStore, *, versions_per_batch: int = 200
) -> IngestSummary:
    summary = IngestSummary()
    ingest_log = log.bind(source=source.name)
    ingest_log.info("ingest.started", versions_per_batch=versions_per_batch)

    runs = [run async for run in page_store.iter_runs(source.name)]
    if runs:
        async with engine.begin() as connection:
            await _upsert_crawl_runs(connection, runs)
    summary.crawl_runs_recorded = len(runs)
    known_run_ids = {run.id for run in runs}

    batch: list[StoredPageVersion] = []
    async for version in page_store.iter_page_versions(source.name):
        summary.page_versions_read += 1
        batch.append(version)
        if len(batch) >= versions_per_batch:
            await _write_batch(engine, source, batch, known_run_ids, summary, ingest_log)
            batch = []
    if batch:
        await _write_batch(engine, source, batch, known_run_ids, summary, ingest_log)

    ingest_log.info(
        "ingest.finished",
        page_versions_read=summary.page_versions_read,
        pages_parsed=summary.pages_parsed,
        pages_unparseable=summary.pages_unparseable,
        events_written=summary.events_written,
        events_with_new_lineups=summary.events_with_new_lineups,
        lineup_slots_written=summary.lineup_slots_written,
        crawl_runs_recorded=summary.crawl_runs_recorded,
    )
    return summary


def _parse_latest_versions(
    source: Source, batch: list[StoredPageVersion], summary: IngestSummary, batch_log: FilteringBoundLogger
) -> list[PageWithEvents]:
    parsed_pages = []
    for version in batch:
        if not version.is_latest:
            continue
        try:
            parsed = source.parse(version.page)
        except Exception:
            summary.pages_unparseable += 1
            batch_log.exception(
                "ingest.parse_failed", url=version.page.url, storage_path=version.storage_path
            )
            continue
        summary.pages_parsed += 1
        parsed_pages.append(PageWithEvents(version.page, parsed.events))
    return parsed_pages


async def _write_batch(
    engine: AsyncEngine,
    source: Source,
    batch: list[StoredPageVersion],
    known_run_ids: set[str],
    summary: IngestSummary,
    batch_log: FilteringBoundLogger,
) -> None:
    parsed_pages = _parse_latest_versions(source, batch, summary, batch_log)
    events_by_source_id = latest_copy_of_each_event(parsed_pages)
    events = [event for event, _ in events_by_source_id.values()]
    planned_slots = [slot for event in events for slot in plan_lineup_slots(event)]

    async with engine.begin() as connection:
        raw_page_ids = await _upsert_raw_pages(connection, source.name, batch, known_run_ids)
        venue_ids = await _upsert_venues(connection, events)
        event_ids = await _upsert_events(
            connection, source.name, events_by_source_id, venue_ids, raw_page_ids
        )
        events_replaced, slots_written = await _replace_changed_lineups(connection, event_ids, planned_slots)

    summary.events_written += len(event_ids)
    summary.events_with_new_lineups += events_replaced
    summary.lineup_slots_written += slots_written
    batch_log.debug(
        "ingest.batch_written",
        page_versions=len(batch),
        events=len(event_ids),
        events_with_new_lineups=events_replaced,
        lineup_slots=slots_written,
    )


async def _upsert_raw_pages(
    connection: AsyncConnection, source_name: str, batch: list[StoredPageVersion], known_run_ids: set[str]
) -> dict[PageVersionKey, int]:
    rows = {
        version_key(version.page): {
            "crawl_run_id": version.page.crawl_run_id if version.page.crawl_run_id in known_run_ids else None,
            "source_name": source_name,
            "url": version.page.url,
            "status": version.page.status,
            "content_type": version.page.content_type,
            "content_sha256": version.page.content_sha256,
            "byte_size": len(version.page.body),
            "fetched_at": version.page.fetched_at,
            "storage_path": version.storage_path,
            "is_latest": version.is_latest,
        }
        for version in batch
    }
    updated_columns = ("crawl_run_id", "status", "content_type", "fetched_at", "storage_path", "is_latest")
    statement = insert(RawPageRow)
    statement = statement.on_conflict_do_update(
        index_elements=["source_name", "url", "content_sha256"],
        set_={column: statement.excluded[column] for column in updated_columns},
    ).returning(RawPageRow.url, RawPageRow.content_sha256, RawPageRow.id)
    result = await connection.execute(statement, list(rows.values()))
    return {(url, content_sha256): page_id for url, content_sha256, page_id in result.all()}


async def _upsert_venues(connection: AsyncConnection, events: list[Event]) -> dict[tuple[str, str], int]:
    details_by_venue: dict[tuple[str, str], dict[str, str | None]] = {}
    for event in events:
        details = details_by_venue.setdefault(
            (event.venue, event.city), {"country_code": None, "timezone": None}
        )
        details["country_code"] = details["country_code"] or event.venue_country_code
        details["timezone"] = details["timezone"] or event.venue_timezone
    if not details_by_venue:
        return {}
    rows = [
        {"name": name, "city": city, **details} for (name, city), details in sorted(details_by_venue.items())
    ]
    statement = insert(VenueRow)
    statement = statement.on_conflict_do_update(
        index_elements=["name", "city"],
        set_={
            "country_code": func.coalesce(statement.excluded.country_code, VenueRow.country_code),
            "timezone": func.coalesce(statement.excluded.timezone, VenueRow.timezone),
        },
    ).returning(VenueRow.name, VenueRow.city, VenueRow.id)
    result = await connection.execute(statement, rows)
    return {(name, city): venue_id for name, city, venue_id in result.all()}


async def _upsert_events(
    connection: AsyncConnection,
    source_name: str,
    events_by_source_id: dict[str, tuple[Event, Page]],
    venue_ids: dict[tuple[str, str], int],
    raw_page_ids: dict[PageVersionKey, int],
) -> dict[str, int]:
    if not events_by_source_id:
        return {}
    rows = [
        {
            "source_name": source_name,
            "source_id": event.source_id,
            "venue_id": venue_ids[(event.venue, event.city)],
            "raw_page_id": raw_page_ids[version_key(page)],
            "title": event.title,
            "url": event.url,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "ra_id": event.ra_id,
        }
        for event, page in events_by_source_id.values()
    ]
    updated_columns = ("venue_id", "raw_page_id", "title", "url", "starts_at", "ends_at", "ra_id")
    statement = insert(EventRow)
    statement = statement.on_conflict_do_update(
        index_elements=["source_name", "source_id"],
        set_={column: statement.excluded[column] for column in updated_columns}
        | {"last_seen_at": func.now()},
    ).returning(EventRow.source_id, EventRow.id)
    result = await connection.execute(statement, rows)
    return {source_id: event_id for source_id, event_id in result.all()}


async def _replace_changed_lineups(
    connection: AsyncConnection, event_ids: dict[str, int], planned_slots: list[PlannedSlot]
) -> tuple[int, int]:
    if not event_ids:
        return 0, 0
    stored = await _stored_lineups(connection, event_ids)
    planned: dict[str, set[SlotContent]] = {source_id: set() for source_id in event_ids}
    for slot in planned_slots:
        planned[slot.event_source_id].add(
            (slot.room, slot.position, slot.raw_text, slot.is_b2b, tuple(slot.tags))
        )
    changed = {
        source_id: event_ids[source_id] for source_id in event_ids if stored[source_id] != planned[source_id]
    }
    if not changed:
        return 0, 0

    await connection.execute(delete(LineupSlotRow).where(is_any_of(LineupSlotRow.event_id, changed.values())))
    rows = [
        {
            "event_id": changed[slot.event_source_id],
            "room": slot.room,
            "position": slot.position,
            "raw_text": slot.raw_text,
            "is_b2b": slot.is_b2b,
            "tags": slot.tags,
        }
        for slot in planned_slots
        if slot.event_source_id in changed
    ]
    if rows:
        await connection.execute(insert(LineupSlotRow), rows)
    return len(changed), len(rows)


async def _stored_lineups(
    connection: AsyncConnection, event_ids: dict[str, int]
) -> dict[str, set[SlotContent]]:
    source_id_by_event_id = {event_id: source_id for source_id, event_id in event_ids.items()}
    stored: dict[str, set[SlotContent]] = {source_id: set() for source_id in event_ids}
    result = await connection.execute(
        select(
            LineupSlotRow.event_id,
            LineupSlotRow.room,
            LineupSlotRow.position,
            LineupSlotRow.raw_text,
            LineupSlotRow.is_b2b,
            LineupSlotRow.tags,
        ).where(is_any_of(LineupSlotRow.event_id, event_ids.values()))
    )
    for event_id, room, position, raw_text, is_b2b, tags in result.all():
        stored[source_id_by_event_id[event_id]].add((room, position, raw_text, is_b2b, tuple(tags)))
    return stored


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
            "error": run.error,
        }
        for run in runs
    ]
    statement = insert(CrawlRunRow)
    statement = statement.on_conflict_do_update(
        index_elements=["id"],
        set_={column: statement.excluded[column] for column in rows[0] if column != "id"},
    )
    await connection.execute(statement, rows)
