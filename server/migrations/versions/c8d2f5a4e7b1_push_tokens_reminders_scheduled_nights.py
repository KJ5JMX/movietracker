"""device tokens, release reminders, scheduled nights, wrapped timestamps

Revision ID: c8d2f5a4e7b1
Revises: b7d3e9a1c2f4
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from alembic import op

revision = "c8d2f5a4e7b1"
down_revision = "b7d3e9a1c2f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_device_token_user"),
            nullable=False,
        ),
        sa.Column("token", sa.String(), nullable=False, unique=True),
        sa.Column(
            "platform", sa.String(), nullable=False, server_default="ios"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_device_tokens_user_id", "device_tokens", ["user_id"]
    )

    with op.batch_alter_table("watchlist_items") as batch:
        batch.add_column(
            sa.Column(
                "remind_release",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "release_reminded",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("watched_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("movie_night_sessions") as batch:
        batch.add_column(
            sa.Column("scheduled_for", sa.DateTime(), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "reminder_sent",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        # Scheduled nights have no pick yet
        batch.alter_column(
            "picked_imdb_id", existing_type=sa.String(), nullable=True
        )
        batch.alter_column(
            "picked_title", existing_type=sa.String(), nullable=True
        )


def downgrade():
    with op.batch_alter_table("movie_night_sessions") as batch:
        batch.alter_column(
            "picked_title", existing_type=sa.String(), nullable=False
        )
        batch.alter_column(
            "picked_imdb_id", existing_type=sa.String(), nullable=False
        )
        batch.drop_column("reminder_sent")
        batch.drop_column("scheduled_for")

    with op.batch_alter_table("watchlist_items") as batch:
        batch.drop_column("watched_at")
        batch.drop_column("created_at")
        batch.drop_column("release_reminded")
        batch.drop_column("remind_release")

    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")
