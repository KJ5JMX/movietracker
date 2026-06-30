"""add users.created_at (member-since date)

Revision ID: a7b8c9d0e1f3
Revises: f6a7b8c9d0e1
Create Date: 2026-06-29 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f3'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('created_at')
