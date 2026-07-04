"""add group_members.position (custom watch order)

Revision ID: e1f2a4b6c7d8
Revises: d0e1f2a4b6c7
Create Date: 2026-07-03 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a4b6c7d8'
down_revision = 'd0e1f2a4b6c7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('group_members', schema=None) as batch_op:
        batch_op.add_column(sa.Column('position', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('group_members', schema=None) as batch_op:
        batch_op.drop_column('position')
