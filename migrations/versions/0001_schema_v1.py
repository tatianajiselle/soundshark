from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artists",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("mbid", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artists")),
        sa.UniqueConstraint("slug", name=op.f("uq_artists_slug")),
    )
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_fetched", sa.Integer(), nullable=False),
        sa.Column("pages_from_store", sa.Integer(), nullable=False),
        sa.Column("pages_failed", sa.Integer(), nullable=False),
        sa.Column("pages_blocked_by_robots", sa.Integer(), nullable=False),
        sa.Column("events_found", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crawl_runs")),
    )
    op.create_index(op.f("ix_crawl_runs_source_name"), "crawl_runs", ["source_name"], unique=False)
    op.create_table(
        "raw_pages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_pages")),
        sa.UniqueConstraint("source_name", "url", name=op.f("uq_raw_pages_source_name_url")),
    )
    op.create_table(
        "venues",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_venues")),
        sa.UniqueConstraint("name", "city", name=op.f("uq_venues_name_city")),
    )
    op.create_table(
        "artist_aliases",
        sa.Column("alias_key", sa.Text(), nullable=False),
        sa.Column("artist_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "origin in ('auto', 'manual')", name=op.f("ck_artist_aliases_origin_is_auto_or_manual")
        ),
        sa.ForeignKeyConstraint(
            ["artist_id"],
            ["artists.id"],
            name=op.f("fk_artist_aliases_artist_id_artists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alias_key", name=op.f("pk_artist_aliases")),
    )
    op.create_index(op.f("ix_artist_aliases_artist_id"), "artist_aliases", ["artist_id"], unique=False)
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("venue_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_page_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ra_id", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["raw_page_id"],
            ["raw_pages.id"],
            name=op.f("fk_events_raw_page_id_raw_pages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name=op.f("fk_events_venue_id_venues")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("source_name", "source_id", name=op.f("uq_events_source_name_source_id")),
    )
    op.create_index(op.f("ix_events_starts_at"), "events", ["starts_at"], unique=False)
    op.create_index(op.f("ix_events_venue_id"), "events", ["venue_id"], unique=False)
    op.create_table(
        "lineup_slots",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("room", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("is_b2b", sa.Boolean(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_lineup_slots_event_id_events"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineup_slots")),
        sa.UniqueConstraint(
            "event_id", "room", "position", name=op.f("uq_lineup_slots_event_id_room_position")
        ),
    )
    op.create_table(
        "credits",
        sa.Column("lineup_slot_id", sa.BigInteger(), nullable=False),
        sa.Column("artist_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artist_id"], ["artists.id"], name=op.f("fk_credits_artist_id_artists"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["lineup_slot_id"],
            ["lineup_slots.id"],
            name=op.f("fk_credits_lineup_slot_id_lineup_slots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("lineup_slot_id", "artist_id", name=op.f("pk_credits")),
    )
    op.create_index(op.f("ix_credits_artist_id"), "credits", ["artist_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_credits_artist_id"), table_name="credits")
    op.drop_table("credits")
    op.drop_table("lineup_slots")
    op.drop_index(op.f("ix_events_venue_id"), table_name="events")
    op.drop_index(op.f("ix_events_starts_at"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_artist_aliases_artist_id"), table_name="artist_aliases")
    op.drop_table("artist_aliases")
    op.drop_table("venues")
    op.drop_table("raw_pages")
    op.drop_index(op.f("ix_crawl_runs_source_name"), table_name="crawl_runs")
    op.drop_table("crawl_runs")
    op.drop_table("artists")
