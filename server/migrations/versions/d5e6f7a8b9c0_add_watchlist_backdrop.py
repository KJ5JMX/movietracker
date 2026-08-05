"""add backdrop column to watchlist_items

Revision ID: d5e6f7a8b9c0
Revises: c4a2b8e1f9d6
Create Date: 2026-08-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4a2b8e1f9d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('watchlist_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('backdrop', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table('watchlist_items', schema=None) as batch_op:
        batch_op.drop_column('backdrop')
