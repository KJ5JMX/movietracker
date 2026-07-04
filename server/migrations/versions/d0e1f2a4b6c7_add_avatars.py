"""add avatars: users.avatar_selected + user_avatars

Revision ID: d0e1f2a4b6c7
Revises: c9d0e1f2a4b6
Create Date: 2026-07-03 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd0e1f2a4b6c7'
down_revision = 'c9d0e1f2a4b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('avatar_selected', sa.String(), nullable=True))

    op.create_table(
        'user_avatars',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('avatar_key', sa.String(), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_avatar_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'avatar_key', name='uq_user_avatar'),
    )
    with op.batch_alter_table('user_avatars', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_avatars_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_avatars', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_avatars_user_id'))
    op.drop_table('user_avatars')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('avatar_selected')
