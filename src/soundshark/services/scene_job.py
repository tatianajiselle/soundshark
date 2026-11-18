import asyncio
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from structlog.typing import FilteringBoundLogger

from soundshark.db import ArtistSceneRow, RelatedArtistRow, SceneRow
from soundshark.db.bulk import copy_into
from soundshark.models.scene_settings import SceneSettings
from soundshark.services.related_lookup import artist_names, artist_nights
from soundshark.services.scenes import detect_scenes

log: FilteringBoundLogger = structlog.get_logger()

SCENE_COLUMNS = ("id", "label", "size", "computed_at")
MEMBER_COLUMNS = ("artist_id", "scene_id")
LARGEST_SHOWN = 5


@dataclass(slots=True)
class SceneSummary:
    artists_in_graph: int = 0
    scenes: int = 0
    artists_placed: int = 0
    largest: list[int] = field(default_factory=list)
    ids_kept: int = 0
    ids_new: int = 0
    ids_retired: int = 0
    clustering_seconds: float = 0.0


async def rebuild_scenes(
    engine: AsyncEngine, settings: SceneSettings | None = None, *, now: datetime | None = None
) -> SceneSummary:
    settings = settings or SceneSettings()
    computed_at = now or datetime.now(UTC)
    summary = SceneSummary()
    log.info("scenes.started", **asdict(settings))

    async with engine.connect() as connection:
        ranked = await load_ranked_related(connection, settings.related_per_artist)
        previous = await load_scene_members(connection)
        nights = await artist_nights(connection)
        names = await artist_names(connection)
    targets = {other_id for others in ranked.values() for other_id, _ in others}
    summary.artists_in_graph = len(set(ranked) | targets)

    started = time.perf_counter()
    scenes = await asyncio.to_thread(detect_scenes, ranked, previous, nights, names, settings)
    summary.clustering_seconds = round(time.perf_counter() - started, 2)

    scene_records = [(scene.id, scene.label, len(scene.members), computed_at) for scene in scenes]
    member_records = sorted((artist_id, scene.id) for scene in scenes for artist_id in scene.members)
    async with engine.begin() as connection:
        await connection.execute(delete(ArtistSceneRow))
        await connection.execute(delete(SceneRow))
        await copy_into(connection, SceneRow.__tablename__, SCENE_COLUMNS, scene_records)
        await copy_into(connection, ArtistSceneRow.__tablename__, MEMBER_COLUMNS, member_records)

    new_ids = {scene.id for scene in scenes}
    summary.scenes = len(scenes)
    summary.artists_placed = len(member_records)
    summary.largest = sorted((len(scene.members) for scene in scenes), reverse=True)[:LARGEST_SHOWN]
    summary.ids_kept = len(new_ids & set(previous))
    summary.ids_new = len(new_ids - set(previous))
    summary.ids_retired = len(set(previous) - new_ids)
    log.info(
        "scenes.finished",
        artists_in_graph=summary.artists_in_graph,
        scenes=summary.scenes,
        artists_placed=summary.artists_placed,
        ids_kept=summary.ids_kept,
        ids_new=summary.ids_new,
        ids_retired=summary.ids_retired,
        clustering_seconds=summary.clustering_seconds,
    )
    return summary


async def load_ranked_related(connection: AsyncConnection, top: int) -> dict[int, list[tuple[int, float]]]:
    result = await connection.execute(
        select(RelatedArtistRow.artist_id, RelatedArtistRow.other_id, RelatedArtistRow.score)
        .where(RelatedArtistRow.rank <= top)
        .order_by(RelatedArtistRow.artist_id, RelatedArtistRow.rank)
    )
    ranked: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for artist_id, other_id, score in result.all():
        ranked[artist_id].append((other_id, score))
    return dict(ranked)


async def load_scene_members(connection: AsyncConnection) -> dict[int, frozenset[int]]:
    members: dict[int, set[int]] = {scene_id: set() for scene_id in await _scene_ids(connection)}
    result = await connection.execute(select(ArtistSceneRow.scene_id, ArtistSceneRow.artist_id))
    for scene_id, artist_id in result.all():
        members[scene_id].add(artist_id)
    return {scene_id: frozenset(artists) for scene_id, artists in members.items()}


async def _scene_ids(connection: AsyncConnection) -> list[int]:
    return list((await connection.execute(select(SceneRow.id))).scalars())
