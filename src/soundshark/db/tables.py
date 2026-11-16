from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONSTRAINT_NAMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class TableBase(DeclarativeBase):
    metadata = MetaData(naming_convention=CONSTRAINT_NAMES)
    type_annotation_map = {datetime: DateTime(timezone=True), str: Text}


def _id_column() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(), primary_key=True)


def _now_by_default() -> Mapped[datetime]:
    return mapped_column(server_default=text("now()"))


class CrawlRunRow(TableBase):
    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(index=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    pages_fetched: Mapped[int]
    pages_from_store: Mapped[int]
    pages_failed: Mapped[int]
    pages_blocked_by_robots: Mapped[int]
    events_found: Mapped[int]


class RawPageRow(TableBase):
    __tablename__ = "raw_pages"
    __table_args__ = (UniqueConstraint("source_name", "url"),)

    id: Mapped[int] = _id_column()
    source_name: Mapped[str]
    url: Mapped[str]
    status: Mapped[int]
    content_type: Mapped[str | None]
    content_sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int]
    fetched_at: Mapped[datetime]


class VenueRow(TableBase):
    __tablename__ = "venues"
    __table_args__ = (UniqueConstraint("name", "city"),)

    id: Mapped[int] = _id_column()
    name: Mapped[str]
    city: Mapped[str]
    country_code: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str | None]


class EventRow(TableBase):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source_name", "source_id"),)

    id: Mapped[int] = _id_column()
    source_name: Mapped[str]
    source_id: Mapped[str]
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    raw_page_id: Mapped[int | None] = mapped_column(ForeignKey("raw_pages.id", ondelete="SET NULL"))
    title: Mapped[str | None]
    url: Mapped[str | None]
    starts_at: Mapped[datetime] = mapped_column(index=True)
    ends_at: Mapped[datetime | None]
    ra_id: Mapped[str | None]
    first_seen_at: Mapped[datetime] = _now_by_default()
    last_seen_at: Mapped[datetime] = _now_by_default()


class LineupSlotRow(TableBase):
    __tablename__ = "lineup_slots"
    __table_args__ = (UniqueConstraint("event_id", "room", "position"),)

    id: Mapped[int] = _id_column()
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    room: Mapped[str]
    position: Mapped[int]
    raw_text: Mapped[str]
    is_b2b: Mapped[bool]
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))


class ArtistRow(TableBase):
    __tablename__ = "artists"

    id: Mapped[int] = _id_column()
    name: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str | None]
    mbid: Mapped[UUID | None]
    created_at: Mapped[datetime] = _now_by_default()


class ArtistAliasRow(TableBase):
    __tablename__ = "artist_aliases"
    __table_args__ = (CheckConstraint("origin in ('auto', 'manual')", name="origin_is_auto_or_manual"),)

    alias_key: Mapped[str] = mapped_column(primary_key=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str]
    origin: Mapped[str]
    created_at: Mapped[datetime] = _now_by_default()


class CreditRow(TableBase):
    __tablename__ = "credits"

    lineup_slot_id: Mapped[int] = mapped_column(
        ForeignKey("lineup_slots.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True, index=True
    )
