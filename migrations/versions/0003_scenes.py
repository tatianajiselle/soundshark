from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenes")),
    )
    op.create_table(
        "artist_scenes",
        sa.Column("artist_id", sa.BigInteger(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artist_id"], ["artists.id"], name=op.f("fk_artist_scenes_artist_id_artists"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"], ["scenes.id"], name=op.f("fk_artist_scenes_scene_id_scenes"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("artist_id", name=op.f("pk_artist_scenes")),
    )
    op.create_index(op.f("ix_artist_scenes_scene_id"), "artist_scenes", ["scene_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_artist_scenes_scene_id"), table_name="artist_scenes")
    op.drop_table("artist_scenes")
    op.drop_table("scenes")
