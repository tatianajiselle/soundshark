import asyncio
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from structlog.typing import FilteringBoundLogger

from soundshark.db import ArtistEdgeRow, CreditRow, EventRow, LineupSlotRow, RelatedArtistRow
from soundshark.models.graph_scoring import GraphScoring
from soundshark.services.artist_graph import CreditOnBill, build_edges, top_related_by_pagerank

log: FilteringBoundLogger = structlog.get_logger()

EDGE_COLUMNS = (
    "a_id",
    "b_id",
    "shared_events",
    "same_room",
    "b2b",
    "first_together",
    "last_together",
    "weight",
)
RELATED_COLUMNS = ("artist_id", "rank", "other_id", "score", "computed_at")


@dataclass(slots=True)
class GraphSummary:
    credits_read: int = 0
    artists_in_graph: int = 0
    edges_written: int = 0
    related_rows_written: int = 0
    scoring_seconds: float = 0.0


async def rebuild_artist_graph(
    engine: AsyncEngine, scoring: GraphScoring | None = None, *, now: datetime | None = None
) -> GraphSummary:
    scoring = scoring or GraphScoring()
    computed_at = now or datetime.now(UTC)
    summary = GraphSummary()
    log.info("graph.started", **asdict(scoring))

    async with engine.connect() as connection:
        credits = await load_credits_on_bills(connection)
    summary.credits_read = len(credits)

    edges = build_edges(credits, scoring, computed_at)
    started = time.perf_counter()
    related = await asyncio.to_thread(top_related_by_pagerank, edges, scoring)
    summary.scoring_seconds = round(time.perf_counter() - started, 2)
    summary.artists_in_graph = len(related)

    edge_records = [tuple(getattr(edge, column) for column in EDGE_COLUMNS) for edge in edges]
    related_records = [
        (artist_id, rank, other_id, score, computed_at)
        for artist_id, ranked in related.items()
        for rank, (other_id, score) in enumerate(ranked, start=1)
    ]
    async with engine.begin() as connection:
        await connection.execute(delete(RelatedArtistRow))
        await connection.execute(delete(ArtistEdgeRow))
        await _copy_into(connection, ArtistEdgeRow.__tablename__, EDGE_COLUMNS, edge_records)
        await _copy_into(connection, RelatedArtistRow.__tablename__, RELATED_COLUMNS, related_records)
    summary.edges_written = len(edge_records)
    summary.related_rows_written = len(related_records)

    log.info(
        "graph.finished",
        credits_read=summary.credits_read,
        artists_in_graph=summary.artists_in_graph,
        edges_written=summary.edges_written,
        related_rows_written=summary.related_rows_written,
        scoring_seconds=summary.scoring_seconds,
    )
    return summary


async def load_credits_on_bills(connection: AsyncConnection) -> list[CreditOnBill]:
    result = await connection.execute(
        select(
            CreditRow.artist_id,
            EventRow.id,
            EventRow.starts_at,
            LineupSlotRow.room,
            LineupSlotRow.id,
            EventRow.venue_id,
        )
        .join(LineupSlotRow, LineupSlotRow.id == CreditRow.lineup_slot_id)
        .join(EventRow, EventRow.id == LineupSlotRow.event_id)
    )
    return [
        CreditOnBill(
            artist_id=artist_id,
            event_id=event_id,
            starts_at=starts_at,
            room=room,
            lineup_slot_id=slot_id,
            venue_id=venue_id,
        )
        for artist_id, event_id, starts_at, room, slot_id, venue_id in result.all()
    ]


async def _copy_into(
    connection: AsyncConnection, table: str, columns: Sequence[str], records: list[tuple[Any, ...]]
) -> None:
    if not records:
        return
    pooled_connection = await connection.get_raw_connection()
    asyncpg_connection = pooled_connection.driver_connection
    if asyncpg_connection is None:
        raise RuntimeError("the database connection was closed before COPY")
    await asyncpg_connection.copy_records_to_table(table, records=records, columns=list(columns))
