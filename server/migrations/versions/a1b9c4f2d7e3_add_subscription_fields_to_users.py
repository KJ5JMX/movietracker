"""add subscription fields to users

Revision ID: a1b9c4f2d7e3
Revises: 557e3dc5ddc9
Create Date: 2026-06-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b9c4f2d7e3'
down_revision = '557e3dc5ddc9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pro_expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column('apple_original_transaction_id', sa.String(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_users_apple_original_transaction_id'),
            ['apple_original_transaction_id'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_apple_original_transaction_id'))
        batch_op.drop_column('apple_original_transaction_id')
        batch_op.drop_column('pro_expires_at')
