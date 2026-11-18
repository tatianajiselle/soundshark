import gzip
import json
import os
import tempfile
import tomllib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlsplit

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from structlog.typing import FilteringBoundLogger

from soundshark.db import ArtistAliasRow, ArtistSceneRow, RelatedArtistRow, SceneRow
from soundshark.interfaces import Source
from soundshark.services.related_lookup import artist_names, artist_nights

log: FilteringBoundLogger = structlog.get_logger()

MAP_VERSION = 1
DEFAULT_MAP_PATH = Path("data/map/map.json")
RELATED_PER_ARTIST = 10
ALIASES_PER_ARTIST = 10
SIGNIFICANT_DIGITS = 6
PUBLISHED_FILE_MODE = 0o644
SCENE_NAMES_ENV_VAR = "SOUNDSHARK_SCENE_NAMES"


class MapCredit(TypedDict):
    name: str
    url: str


class MapScene(TypedDict):
    id: int
    label: str
    size: int


class MapArtist(TypedDict):
    id: int
    name: str
    aliases: list[str]
    nights: int
    scene: int | None


class MapFile(TypedDict):
    version: int
    generated_at: str
    credits: list[MapCredit]
    scenes: list[MapScene]
    artists: list[MapArtist]
    related: list[list[int | float]]


@dataclass(frozen=True, slots=True)
class MapRows:
    names: Mapping[int, str]
    aliases: Mapping[int, Sequence[str]]
    nights: Mapping[int, int]
    scene_of: Mapping[int, int]
    scenes: Sequence[tuple[int, str, int]]
    related: Sequence[tuple[int, int, int, float]]


@dataclass(frozen=True, slots=True)
class MapSummary:
    path: Path
    gzip_path: Path
    artists: int
    scenes: int
    related: int
    credits: int
    bytes_written: int
    gzip_bytes_written: int


def source_credits(sources: Iterable[Source]) -> list[MapCredit]:
    credits: list[MapCredit] = []
    for source in sources:
        if not source.seed_urls:
            continue
        seed = urlsplit(source.seed_urls[0])
        credits.append({"name": source.name, "url": f"{seed.scheme}://{seed.netloc}/"})
    return credits


def other_spellings(name: str, display_names: Iterable[str]) -> list[str]:
    seen = {name.casefold()}
    spellings: list[str] = []
    for display_name in sorted(display_names, key=lambda n: (n.casefold(), n)):
        key = display_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        spellings.append(display_name)
    return spellings[:ALIASES_PER_ARTIST]


def load_scene_names(path: Path) -> dict[int, str]:
    table = tomllib.loads(path.read_text(encoding="utf-8")).get("names", {})
    if not isinstance(table, dict):
        raise ValueError(f"{path}: [names] must be a table of scene id = name")
    names: dict[int, str] = {}
    for key, name in table.items():
        if not key.isdigit() or not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}: {key!r} = {name!r} must be a scene id and a non-empty name")
        names[int(key)] = name.strip()
    return names


def scene_names_from_env() -> dict[int, str]:
    path = os.environ.get(SCENE_NAMES_ENV_VAR, "").strip()
    return load_scene_names(Path(path)) if path else {}


def rounded_score(score: float) -> float:
    return float(f"{score:.{SIGNIFICANT_DIGITS}g}")


def build_map(
    rows: MapRows,
    credits: Sequence[MapCredit],
    generated_at: datetime,
    scene_names: Mapping[int, str] | None = None,
) -> MapFile:
    names = scene_names or {}
    top_related = sorted(
        (artist_id, rank, other_id, score)
        for artist_id, rank, other_id, score in rows.related
        if rank <= RELATED_PER_ARTIST
    )
    artist_ids = sorted(
        {artist_id for artist_id, _, _, _ in rows.related} | {other_id for _, _, other_id, _ in top_related}
    )
    artists = [
        MapArtist(
            id=artist_id,
            name=rows.names[artist_id],
            aliases=other_spellings(rows.names[artist_id], rows.aliases.get(artist_id, ())),
            nights=rows.nights.get(artist_id, 0),
            scene=rows.scene_of.get(artist_id),
        )
        for artist_id in artist_ids
    ]
    scenes = [
        MapScene(id=scene_id, label=names.get(scene_id, label), size=size)
        for scene_id, label, size in sorted(rows.scenes, key=lambda scene: (-scene[2], scene[0]))
    ]
    return MapFile(
        version=MAP_VERSION,
        generated_at=generated_at.astimezone(UTC).isoformat(timespec="seconds"),
        credits=[MapCredit(name=credit["name"], url=credit["url"]) for credit in credits],
        scenes=scenes,
        artists=artists,
        related=[
            [artist_id, other_id, rounded_score(score)] for artist_id, _, other_id, score in top_related
        ],
    )


def map_bytes(payload: MapFile) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def write_map(payload: MapFile, path: Path) -> tuple[Path, Path]:
    data = map_bytes(payload)
    gzip_path = path.with_name(path.name + ".gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        staged.append((_stage(path, data), path))
        staged.append((_stage(gzip_path, gzip.compress(data, compresslevel=9, mtime=0)), gzip_path))
        for temporary, final in staged:
            os.replace(temporary, final)
    except BaseException:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        raise
    return path, gzip_path


def _stage(path: Path, data: bytes) -> Path:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
            os.chmod(temporary, PUBLISHED_FILE_MODE)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    return temporary


async def load_map_rows(connection: AsyncConnection) -> MapRows:
    aliases: dict[int, list[str]] = defaultdict(list)
    for artist_id, display_name in (
        await connection.execute(select(ArtistAliasRow.artist_id, ArtistAliasRow.display_name))
    ).all():
        aliases[artist_id].append(display_name)
    members = await connection.execute(select(ArtistSceneRow.artist_id, ArtistSceneRow.scene_id))
    scenes = await connection.execute(select(SceneRow.id, SceneRow.label, SceneRow.size))
    related = await connection.execute(
        select(
            RelatedArtistRow.artist_id,
            RelatedArtistRow.rank,
            RelatedArtistRow.other_id,
            RelatedArtistRow.score,
        )
    )
    return MapRows(
        names=await artist_names(connection),
        aliases=aliases,
        nights=await artist_nights(connection),
        scene_of={artist_id: scene_id for artist_id, scene_id in members.all()},
        scenes=[(scene_id, label, size) for scene_id, label, size in scenes.all()],
        related=[(artist_id, rank, other_id, score) for artist_id, rank, other_id, score in related.all()],
    )


async def export_map(
    engine: AsyncEngine,
    sources: Iterable[Source],
    path: Path = DEFAULT_MAP_PATH,
    *,
    now: datetime | None = None,
    scene_names: Mapping[int, str] | None = None,
) -> MapSummary:
    credits = source_credits(sources)
    async with engine.connect() as connection:
        rows = await load_map_rows(connection)
    payload = build_map(rows, credits, now or datetime.now(UTC), scene_names)
    path, gzip_path = write_map(payload, path)
    summary = MapSummary(
        path=path,
        gzip_path=gzip_path,
        artists=len(payload["artists"]),
        scenes=len(rows.scenes),
        related=len(payload["related"]),
        credits=len(credits),
        bytes_written=path.stat().st_size,
        gzip_bytes_written=gzip_path.stat().st_size,
    )
    log.info(
        "map.exported",
        path=str(path),
        artists=summary.artists,
        scenes=summary.scenes,
        related=summary.related,
        credits=summary.credits,
        bytes_written=summary.bytes_written,
        gzip_bytes_written=summary.gzip_bytes_written,
    )
    return summary
