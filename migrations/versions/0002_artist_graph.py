from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artist_edges",
        sa.Column("a_id", sa.BigInteger(), nullable=False),
        sa.Column("b_id", sa.BigInteger(), nullable=False),
        sa.Column("shared_events", sa.Integer(), nullable=False),
        sa.Column("same_room", sa.Integer(), nullable=False),
        sa.Column("b2b", sa.Integer(), nullable=False),
        sa.Column("first_together", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_together", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight", sa.Double(), nullable=False),
        sa.CheckConstraint("a_id < b_id", name=op.f("ck_artist_edges_each_pair_stored_once")),
        sa.ForeignKeyConstraint(
            ["a_id"], ["artists.id"], name=op.f("fk_artist_edges_a_id_artists"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["b_id"], ["artists.id"], name=op.f("fk_artist_edges_b_id_artists"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("a_id", "b_id", name=op.f("pk_artist_edges")),
    )
    op.create_index(op.f("ix_artist_edges_b_id"), "artist_edges", ["b_id"], unique=False)
    op.create_table(
        "related_artists",
        sa.Column("artist_id", sa.BigInteger(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("other_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Double(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artist_id"],
            ["artists.id"],
            name=op.f("fk_related_artists_artist_id_artists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["other_id"], ["artists.id"], name=op.f("fk_related_artists_other_id_artists"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("artist_id", "rank", name=op.f("pk_related_artists")),
    )


def downgrade() -> None:
    op.drop_table("related_artists")
    op.drop_index(op.f("ix_artist_edges_b_id"), table_name="artist_edges")
    op.drop_table("artist_edges")
