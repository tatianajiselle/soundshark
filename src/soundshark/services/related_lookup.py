from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from soundshark.db import (
    ArtistAliasRow,
    ArtistEdgeRow,
    ArtistRow,
    CreditRow,
    EventRow,
    LineupSlotRow,
    RelatedArtistRow,
    VenueRow,
)
from soundshark.services.artist_identity import matching_key


@dataclass(frozen=True, slots=True)
class ArtistOverview:
    id: int
    name: str
    nights: int
    first_night: datetime | None
    last_night: datetime | None


@dataclass(frozen=True, slots=True)
class RelatedArtist:
    rank: int
    name: str
    score: float
    nights_together: int
    same_room: int
    b2b: int
    last_together: datetime | None


@dataclass(frozen=True, slots=True)
class RelatedArtists:
    artist: ArtistOverview
    related: list[RelatedArtist]
    computed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ArtistNotFound:
    query: str
    did_you_mean: list[str]


async def related_artists(
    engine: AsyncEngine, name: str, *, limit: int = 20
) -> RelatedArtists | ArtistNotFound:
    async with engine.connect() as connection:
        artist_id = await _artist_id_for(connection, name)
        if artist_id is None:
            return ArtistNotFound(query=name, did_you_mean=await _similar_names(connection, name))
        overview = await _overview(connection, artist_id)
        related, computed_at = await _related(connection, artist_id, limit)
    return RelatedArtists(artist=overview, related=related, computed_at=computed_at)


async def _artist_id_for(connection: AsyncConnection, name: str) -> int | None:
    result = await connection.execute(
        select(ArtistAliasRow.artist_id).where(ArtistAliasRow.alias_key == matching_key(name))
    )
    return result.scalar_one_or_none()


async def _similar_names(connection: AsyncConnection, name: str, how_many: int = 5) -> list[str]:
    key = matching_key(name)
    result = await connection.execute(
        select(ArtistAliasRow.display_name)
        .where(ArtistAliasRow.alias_key.op("%")(key))
        .order_by(func.similarity(ArtistAliasRow.alias_key, key).desc(), ArtistAliasRow.display_name)
        .limit(how_many)
    )
    return list(result.scalars())


async def _overview(connection: AsyncConnection, artist_id: int) -> ArtistOverview:
    name = (await connection.execute(select(ArtistRow.name).where(ArtistRow.id == artist_id))).scalar_one()
    nights, first_night, last_night = (
        await connection.execute(
            select(
                func.count(func.distinct(EventRow.id)),
                func.min(EventRow.starts_at),
                func.max(EventRow.starts_at),
            )
            .join(LineupSlotRow, LineupSlotRow.event_id == EventRow.id)
            .join(CreditRow, CreditRow.lineup_slot_id == LineupSlotRow.id)
            .where(CreditRow.artist_id == artist_id)
        )
    ).one()
    return ArtistOverview(artist_id, name, nights, first_night, last_night)


async def _related(
    connection: AsyncConnection, artist_id: int, limit: int
) -> tuple[list[RelatedArtist], datetime | None]:
    edge_with_this_artist = and_(
        ArtistEdgeRow.a_id == func.least(RelatedArtistRow.artist_id, RelatedArtistRow.other_id),
        ArtistEdgeRow.b_id == func.greatest(RelatedArtistRow.artist_id, RelatedArtistRow.other_id),
    )
    result = await connection.execute(
        select(
            RelatedArtistRow.rank,
            ArtistRow.name,
            RelatedArtistRow.score,
            ArtistEdgeRow.shared_events,
            ArtistEdgeRow.same_room,
            ArtistEdgeRow.b2b,
            ArtistEdgeRow.last_together,
            RelatedArtistRow.computed_at,
        )
        .join(ArtistRow, ArtistRow.id == RelatedArtistRow.other_id)
        .outerjoin(ArtistEdgeRow, edge_with_this_artist)
        .where(RelatedArtistRow.artist_id == artist_id)
        .order_by(RelatedArtistRow.rank)
        .limit(limit)
    )
    rows = result.all()
    related = [
        RelatedArtist(
            rank=rank,
            name=name,
            score=score,
            nights_together=shared_events or 0,
            same_room=same_room or 0,
            b2b=b2b or 0,
            last_together=last_together,
        )
        for rank, name, score, shared_events, same_room, b2b, last_together, _ in rows
    ]
    return related, rows[0][-1] if rows else None


async def artist_names(connection: AsyncConnection) -> dict[int, str]:
    result = await connection.execute(select(ArtistRow.id, ArtistRow.name))
    return {artist_id: name for artist_id, name in result.all()}


async def artist_nights(connection: AsyncConnection) -> dict[int, int]:
    result = await connection.execute(
        select(CreditRow.artist_id, func.count(func.distinct(LineupSlotRow.event_id)))
        .join(LineupSlotRow, LineupSlotRow.id == CreditRow.lineup_slot_id)
        .group_by(CreditRow.artist_id)
    )
    return {artist_id: nights for artist_id, nights in result.all()}


async def artist_cities(connection: AsyncConnection) -> dict[int, list[str]]:
    nights = func.count(func.distinct(LineupSlotRow.event_id))
    result = await connection.execute(
        select(CreditRow.artist_id, VenueRow.city, nights)
        .join(LineupSlotRow, LineupSlotRow.id == CreditRow.lineup_slot_id)
        .join(EventRow, EventRow.id == LineupSlotRow.event_id)
        .join(VenueRow, VenueRow.id == EventRow.venue_id)
        .group_by(CreditRow.artist_id, VenueRow.city)
        .order_by(CreditRow.artist_id, nights.desc(), VenueRow.city)
    )
    cities: dict[int, list[str]] = defaultdict(list)
    for artist_id, city, _ in result.all():
        cities[artist_id].append(city)
    return dict(cities)
