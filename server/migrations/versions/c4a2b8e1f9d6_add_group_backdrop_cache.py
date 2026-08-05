"""add franchise backdrop cache columns to groups

Revision ID: c4a2b8e1f9d6
Revises: b3f1c7a9d2e5
Create Date: 2026-08-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a2b8e1f9d6'
down_revision = 'b3f1c7a9d2e5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('backdrop_url', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('backdrop_key', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_column('backdrop_key')
        batch_op.drop_column('backdrop_url')
