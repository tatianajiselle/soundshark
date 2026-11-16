from sqlalchemy import func, select

from soundshark.db import ArtistEdgeRow, RelatedArtistRow
from soundshark.services.credits import build_credits
from soundshark.services.graph_job import rebuild_artist_graph
from soundshark.services.ingest import ingest_stored_pages
from soundshark.services.related_lookup import ArtistNotFound, RelatedArtists, related_artists
from soundshark.sources import DemoSource
from tests.fakes import crawl_demo_into_memory


async def build_demo_graph(engine) -> None:
    await ingest_stored_pages(engine, DemoSource(), await crawl_demo_into_memory())
    await build_credits(engine)
    await rebuild_artist_graph(engine)


async def count(engine, table) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(select(func.count()).select_from(table))).scalar_one()


async def test_graph_stores_every_pair_and_ranked_related_artists(engine):
    await build_demo_graph(engine)
    assert await count(engine, ArtistEdgeRow) == 19
    async with engine.connect() as connection:
        longest = (
            await connection.execute(
                select(func.count()).select_from(RelatedArtistRow).group_by(RelatedArtistRow.artist_id)
            )
        ).scalars()
    assert max(longest) == 7


async def test_rebuilding_the_graph_gives_the_same_rows(engine):
    await build_demo_graph(engine)
    first = (await count(engine, ArtistEdgeRow), await count(engine, RelatedArtistRow))
    await rebuild_artist_graph(engine)
    assert (await count(engine, ArtistEdgeRow), await count(engine, RelatedArtistRow)) == first


async def test_related_shows_the_evidence_for_each_answer(engine):
    await build_demo_graph(engine)
    answer = await related_artists(engine, "  ora VANCE ")
    assert isinstance(answer, RelatedArtists)
    assert (answer.artist.name, answer.artist.nights) == ("Ora Vance", 2)
    juno = next(r for r in answer.related if r.name == "Juno Hale")
    assert (juno.nights_together, juno.same_room, juno.b2b) == (2, 1, 1)
    assert answer.related[0].name in {"Juno Hale", "Mirek Sol"}
    assert [r.rank for r in answer.related] == list(range(1, len(answer.related) + 1))


async def test_artists_connected_only_through_others_are_related_too(engine):
    await build_demo_graph(engine)
    answer = await related_artists(engine, "Ora Vance")
    assert isinstance(answer, RelatedArtists)
    selene = next(r for r in answer.related if r.name == "Selene Mau")
    assert selene.nights_together == 0
    assert selene.score > 0


async def test_unknown_names_get_suggestions(engine):
    await build_demo_graph(engine)
    answer = await related_artists(engine, "Ora Vanse")
    assert isinstance(answer, ArtistNotFound)
    assert answer.did_you_mean[0] == "Ora Vance"
