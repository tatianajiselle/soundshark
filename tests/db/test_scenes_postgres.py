from datetime import UTC, datetime

from sqlalchemy import delete, select

from soundshark.db import ArtistRow, ArtistSceneRow, RelatedArtistRow, SceneRow
from soundshark.models.scene_settings import SceneSettings
from soundshark.services.scene_job import rebuild_scenes
from tests.db.scene_data import insert_planted_graph
from tests.db.test_graph_postgres import build_demo_graph

NOW = datetime(2031, 3, 4, 5, 6, tzinfo=UTC)
SMALL = SceneSettings(min_scene_size=5, resolution=1.0)


async def stored_scenes(engine) -> dict[int, tuple[str, int, frozenset[int]]]:
    async with engine.connect() as connection:
        scenes = (await connection.execute(select(SceneRow.id, SceneRow.label, SceneRow.size))).all()
        members = (await connection.execute(select(ArtistSceneRow.scene_id, ArtistSceneRow.artist_id))).all()
    return {
        scene_id: (label, size, frozenset(a for s, a in members if s == scene_id))
        for scene_id, label, size in scenes
    }


async def test_the_demo_graph_gets_scenes_with_labels(engine):
    await build_demo_graph(engine)
    summary = await rebuild_scenes(engine, SceneSettings(min_scene_size=2, resolution=1.0), now=NOW)
    scenes = await stored_scenes(engine)
    assert summary.scenes == len(scenes) > 0
    assert summary.artists_placed == sum(len(members) for _, _, members in scenes.values())
    async with engine.connect() as connection:
        names = {a: n for a, n in (await connection.execute(select(ArtistRow.id, ArtistRow.name))).all()}
        computed = set((await connection.execute(select(SceneRow.computed_at))).scalars())
    assert computed == {NOW}
    for label, size, members in scenes.values():
        assert size == len(members)
        assert set(label.split(" / ")) <= {names[a] for a in members}


async def test_planted_scenes_are_stored_and_keep_their_ids(engine):
    groups = await insert_planted_graph(engine, [40, 30, 20])
    first = await rebuild_scenes(engine, SMALL, now=NOW)
    assert (first.scenes, first.artists_placed, first.largest) == (3, 90, [40, 30, 20])
    assert (first.ids_kept, first.ids_new, first.ids_retired) == (0, 3, 0)
    stored = await stored_scenes(engine)
    assert sorted(members for _, _, members in stored.values()) == sorted(groups)

    again = await rebuild_scenes(engine, SMALL, now=NOW)
    assert (again.ids_kept, again.ids_new, again.ids_retired) == (3, 0, 0)
    assert await stored_scenes(engine) == stored


async def test_a_scene_that_disappears_is_retired_and_its_rows_go(engine):
    groups = await insert_planted_graph(engine, [40, 30, 20])
    await rebuild_scenes(engine, SMALL, now=NOW)
    before = await stored_scenes(engine)
    smallest = groups[2]
    async with engine.begin() as connection:
        await connection.execute(delete(ArtistRow).where(ArtistRow.id.in_(smallest)))
    summary = await rebuild_scenes(engine, SMALL, now=NOW)
    after = await stored_scenes(engine)
    assert (summary.ids_kept, summary.ids_new, summary.ids_retired) == (2, 0, 1)
    assert after == {scene_id: scene for scene_id, scene in before.items() if scene[2] != smallest}


async def test_no_related_artists_means_no_scenes(engine):
    await insert_planted_graph(engine, [20, 20])
    await rebuild_scenes(engine, SMALL, now=NOW)
    async with engine.begin() as connection:
        await connection.execute(delete(RelatedArtistRow))
    summary = await rebuild_scenes(engine, SMALL, now=NOW)
    assert (summary.scenes, summary.artists_placed, summary.ids_retired) == (0, 0, 2)
    assert await stored_scenes(engine) == {}
