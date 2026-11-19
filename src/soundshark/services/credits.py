from collections.abc import Iterable
from dataclasses import dataclass

import structlog
from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from structlog.typing import FilteringBoundLogger

from soundshark.db import ArtistAliasRow, ArtistRow, CreditRow, LineupSlotRow
from soundshark.db.bulk import is_any_of
from soundshark.services.artist_identity import matching_key, split_lineup_slot
from soundshark.utils.slugs import slug_with_short_hash, slugify

log: FilteringBoundLogger = structlog.get_logger()


@dataclass(slots=True)
class CreditSummary:
    lineup_slots_read: int = 0
    credits_written: int = 0
    artists_created: int = 0
    automatic_aliases_removed: int = 0
    artists_removed: int = 0


def choose_new_artist_slugs(new_keys: Iterable[str], slugs_already_taken: set[str]) -> dict[str, str]:
    taken = set(slugs_already_taken)
    slug_by_key = {}
    for key in new_keys:
        slug = slugify(key)
        if not slug or slug in taken:
            slug = slug_with_short_hash(key)
        taken.add(slug)
        slug_by_key[key] = slug
    return slug_by_key


async def build_credits(
    engine: AsyncEngine, *, rebuild: bool = False, slots_per_batch: int = 2000
) -> CreditSummary:
    summary = CreditSummary()
    log.info("credits.started", rebuild=rebuild)
    if rebuild:
        async with engine.begin() as connection:
            await _forget_automatic_matches(connection, summary)

    last_slot_id = 0
    while True:
        async with engine.begin() as connection:
            slots = await _uncredited_slots_after(connection, last_slot_id, slots_per_batch)
            if not slots:
                break
            last_slot_id = slots[-1][0]
            await _credit_slots(connection, slots, summary)
        summary.lineup_slots_read += len(slots)

    log.info(
        "credits.finished",
        rebuild=rebuild,
        lineup_slots_read=summary.lineup_slots_read,
        credits_written=summary.credits_written,
        artists_created=summary.artists_created,
        automatic_aliases_removed=summary.automatic_aliases_removed,
        artists_removed=summary.artists_removed,
    )
    return summary


async def _forget_automatic_matches(connection: AsyncConnection, summary: CreditSummary) -> None:
    await connection.execute(delete(CreditRow))
    removed_aliases = await connection.execute(
        delete(ArtistAliasRow).where(ArtistAliasRow.origin == "auto").returning(ArtistAliasRow.alias_key)
    )
    summary.automatic_aliases_removed = len(removed_aliases.all())
    artist_has_an_alias = exists().where(ArtistAliasRow.artist_id == ArtistRow.id)
    removed_artists = await connection.execute(
        delete(ArtistRow).where(~artist_has_an_alias).returning(ArtistRow.id)
    )
    summary.artists_removed = len(removed_artists.all())


async def _uncredited_slots_after(
    connection: AsyncConnection, last_slot_id: int, limit: int
) -> list[tuple[int, str]]:
    slot_has_a_credit = exists().where(CreditRow.lineup_slot_id == LineupSlotRow.id)
    result = await connection.execute(
        select(LineupSlotRow.id, LineupSlotRow.raw_text)
        .where(LineupSlotRow.id > last_slot_id, ~slot_has_a_credit)
        .order_by(LineupSlotRow.id)
        .limit(limit)
    )
    return [(slot_id, raw_text) for slot_id, raw_text in result.all()]


async def _credit_slots(
    connection: AsyncConnection, slots: list[tuple[int, str]], summary: CreditSummary
) -> None:
    acts_by_slot_id = {slot_id: split_lineup_slot(raw_text).acts for slot_id, raw_text in slots}
    display_name_by_key: dict[str, str] = {}
    for acts in acts_by_slot_id.values():
        for act in acts:
            display_name_by_key.setdefault(matching_key(act), act)
    if not display_name_by_key:
        return

    artist_id_by_key, created = await _artist_ids_creating_missing(connection, display_name_by_key)
    summary.artists_created += created
    credits = sorted(
        {
            (slot_id, artist_id_by_key[matching_key(act)])
            for slot_id, acts in acts_by_slot_id.items()
            for act in acts
        }
    )
    await connection.execute(
        insert(CreditRow).on_conflict_do_nothing(),
        [{"lineup_slot_id": slot_id, "artist_id": artist_id} for slot_id, artist_id in credits],
    )
    summary.credits_written += len(credits)


async def _artist_ids_creating_missing(
    connection: AsyncConnection, display_name_by_key: dict[str, str]
) -> tuple[dict[str, int], int]:
    known = await connection.execute(
        select(ArtistAliasRow.alias_key, ArtistAliasRow.artist_id).where(
            is_any_of(ArtistAliasRow.alias_key, display_name_by_key)
        )
    )
    artist_id_by_key = {key: artist_id for key, artist_id in known.all()}
    new_keys = [key for key in display_name_by_key if key not in artist_id_by_key]
    if not new_keys:
        return artist_id_by_key, 0

    candidate_slugs = {slugify(key) for key in new_keys}
    taken = await connection.execute(select(ArtistRow.slug).where(is_any_of(ArtistRow.slug, candidate_slugs)))
    slug_by_key = choose_new_artist_slugs(new_keys, set(taken.scalars().all()))
    created = await connection.execute(
        insert(ArtistRow).returning(ArtistRow.slug, ArtistRow.id),
        [{"name": display_name_by_key[key], "slug": slug_by_key[key]} for key in new_keys],
    )
    key_by_slug = {slug: key for key, slug in slug_by_key.items()}
    new_artist_ids = {key_by_slug[slug]: artist_id for slug, artist_id in created.all()}
    await connection.execute(
        insert(ArtistAliasRow).on_conflict_do_nothing(index_elements=["alias_key"]),
        [
            {
                "alias_key": key,
                "artist_id": artist_id,
                "display_name": display_name_by_key[key],
                "origin": "auto",
            }
            for key, artist_id in new_artist_ids.items()
        ],
    )
    return artist_id_by_key | new_artist_ids, len(new_artist_ids)
