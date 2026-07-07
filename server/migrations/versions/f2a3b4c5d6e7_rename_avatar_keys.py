"""rename avatar keys to match new display names

Revision ID: f2a3b4c5d6e7
Revises: e1f2a4b6c7d8
Create Date: 2026-07-05

Renames the stored avatar keys so each key matches its new display name.
Two columns hold an avatar key: users.avatar_selected (the equipped avatar)
and user_avatars.avatar_key (each owned avatar). The map is strictly 1:1 and
the new keys do not collide with any existing key, so the uq_user_avatar
(user_id, avatar_key) constraint is never violated. Fully reversible.
"""
from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a4b6c7d8"
branch_labels = None
depends_on = None


# old key -> new key. Keys not listed here were never renamed.
KEY_RENAMES = {
    "couch": "couch_potato",
    "popcorn": "popcorn_enthusiast",
    "host": "concierge",
    "ticket": "golden_ticket",
    "shoes": "ruby_slippers",
    "shorts": "carls_boxers",
    "ball": "wilson",
    "house": "up",
    "ranger": "space_ranger",
    "noir": "detective",
    "blade": "the_force",
    "hammer": "mjolnir",
    "idol": "golden_idol",
    "wizard": "merlin",
    "vampire": "dracula",
    "raptor": "clever_girl",
    "gauntlet": "infinity_gauntlet",
    "ring": "the_one_ring",
}


def _remap(mapping):
    conn = op.get_bind()
    for old, new in mapping.items():
        conn.execute(
            sa.text(
                "UPDATE users SET avatar_selected = :new "
                "WHERE avatar_selected = :old"
            ),
            {"new": new, "old": old},
        )
        conn.execute(
            sa.text(
                "UPDATE user_avatars SET avatar_key = :new "
                "WHERE avatar_key = :old"
            ),
            {"new": new, "old": old},
        )


def upgrade():
    _remap(KEY_RENAMES)


def downgrade():
    _remap({new: old for old, new in KEY_RENAMES.items()})
