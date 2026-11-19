import gzip
import json
from datetime import UTC, datetime

from sqlalchemy import func, insert, select

from soundshark.db import ArtistAliasRow, ArtistSceneRow, RelatedArtistRow
from soundshark.models.scene_settings import SceneSettings
from soundshark.services.artist_identity import matching_key
from soundshark.services.map_export import export_map
from soundshark.services.scene_job import rebuild_scenes
from soundshark.sources import DemoSource
from tests.db.test_graph_postgres import build_demo_graph
from tests.map_contract import assert_map_contract

NOW = datetime(2031, 3, 4, 5, 6, 7, tzinfo=UTC)
NOT_PUBLISHED = ("Kelvin Hall", "The Cistern", "Annex", "Basement", "2026-0", "b2b")


async def test_the_exported_map_keeps_to_the_contract(engine, tmp_path):
    await build_demo_graph(engine)
    await rebuild_scenes(engine, SceneSettings(min_scene_size=2), now=NOW)
    async with engine.begin() as connection:
        ora_key = ArtistAliasRow.alias_key == matching_key("Ora Vance")
        ora = (await connection.execute(select(ArtistAliasRow.artist_id).where(ora_key))).scalar_one()
        await connection.execute(
            insert(ArtistAliasRow),
            [
                {"alias_key": key, "artist_id": ora, "display_name": spelling, "origin": "manual"}
                for key, spelling in (("ora v", "Ora V."), ("ora vance shouting", "ORA VANCE"))
            ],
        )
        related_sources = (
            await connection.execute(select(func.count(func.distinct(RelatedArtistRow.artist_id))))
        ).scalar_one()
        scene_rows = await connection.execute(select(ArtistSceneRow.artist_id, ArtistSceneRow.scene_id))
        placed = {artist_id: scene_id for artist_id, scene_id in scene_rows.all()}

    summary = await export_map(engine, [DemoSource()], tmp_path / "map" / "map.json", now=NOW)

    text = summary.path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert_map_contract(payload)
    assert gzip.decompress(summary.gzip_path.read_bytes()) == summary.path.read_bytes()
    assert payload["generated_at"] == "2031-03-04T05:06:07+00:00"
    assert payload["credits"] == [{"name": "demo", "url": "https://demo.soundshark.test/"}]
    artists = {artist["id"]: artist for artist in payload["artists"]}
    assert len(artists) == related_sources == summary.artists
    assert artists[ora]["name"] == "Ora Vance"
    assert artists[ora]["aliases"] == ["Ora V."]
    assert artists[ora]["nights"] == 2
    assert set(artists[ora]["cities"]) <= {"Lakeport", "Northvale"} and artists[ora]["cities"]
    assert all(len(set(artist["cities"])) == len(artist["cities"]) for artist in artists.values())
    assert {a: artist["scene"] for a, artist in artists.items() if artist["scene"] is not None} == placed
    assert [scene["size"] for scene in payload["scenes"]] == sorted(
        (scene["size"] for scene in payload["scenes"]), reverse=True
    )
    assert len(payload["related"]) == summary.related
    assert all(len([p for p in payload["related"] if p[0] == a]) <= 10 for a in artists)
    for forbidden in NOT_PUBLISHED:
        assert forbidden not in text
