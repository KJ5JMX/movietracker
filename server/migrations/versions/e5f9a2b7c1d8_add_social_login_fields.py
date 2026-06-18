"""add social login fields to users

Revision ID: e5f9a2b7c1d8
Revises: d4e8f1a2c3b5
Create Date: 2026-06-17 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f9a2b7c1d8'
down_revision = 'd4e8f1a2c3b5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('apple_sub', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('google_sub', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('onboarded', sa.Boolean(), server_default='1', nullable=False))
        batch_op.create_index(batch_op.f('ix_users_apple_sub'), ['apple_sub'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_google_sub'), ['google_sub'], unique=True)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_google_sub'))
        batch_op.drop_index(batch_op.f('ix_users_apple_sub'))
        batch_op.drop_column('onboarded')
        batch_op.drop_column('google_sub')
        batch_op.drop_column('apple_sub')
