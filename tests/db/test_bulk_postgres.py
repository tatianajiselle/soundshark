from sqlalchemy import insert, select

from soundshark.db import VenueRow
from soundshark.db.bulk import is_any_of

MORE_THAN_THE_DRIVER_ALLOWS = 40_000


async def test_is_any_of_takes_more_values_than_query_arguments_allow(engine):
    async with engine.begin() as connection:
        await connection.execute(
            insert(VenueRow), [{"name": f"Hall {n}", "city": "Testville"} for n in range(3)]
        )
        ids = (await connection.execute(select(VenueRow.id))).scalars().all()
        wanted = [*ids[:2], *range(10**9, 10**9 + MORE_THAN_THE_DRIVER_ALLOWS)]
        found = (
            await connection.execute(select(VenueRow.id).where(is_any_of(VenueRow.id, wanted)))
        ).scalars()
        names = (
            await connection.execute(
                select(VenueRow.name).where(is_any_of(VenueRow.name, [f"Hall {n}" for n in range(1, 40_000)]))
            )
        ).scalars()
        assert sorted(found.all()) == sorted(ids[:2])
        assert sorted(names.all()) == ["Hall 1", "Hall 2"]
