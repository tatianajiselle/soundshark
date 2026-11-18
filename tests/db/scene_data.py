from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from soundshark.db import ArtistRow, RelatedArtistRow
from tests.services.test_scenes import planted_related

COMPUTED_AT = datetime(2031, 1, 1, tzinfo=UTC)


async def insert_planted_graph(engine: AsyncEngine, group_sizes: list[int]) -> list[frozenset[int]]:
    ranked, groups = planted_related(group_sizes)
    artists = [{"id": a, "name": f"Planted {a:03}", "slug": f"planted-{a:03}"} for a in sorted(ranked)]
    related = [
        {"artist_id": a, "rank": rank, "other_id": other, "score": score, "computed_at": COMPUTED_AT}
        for a, rows in ranked.items()
        for rank, (other, score) in enumerate(rows, start=1)
    ]
    async with engine.begin() as connection:
        await connection.execute(insert(ArtistRow), artists)
        await connection.execute(insert(RelatedArtistRow), related)
    return groups
