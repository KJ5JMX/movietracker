"""add groups and group_members (user-created collections)

Revision ID: b8c9d0e1f2a4
Revises: a7b8c9d0e1f3
Create Date: 2026-07-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a4'
down_revision = 'a7b8c9d0e1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_group_user'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_groups_user_id'), ['user_id'], unique=False)

    op.create_table(
        'group_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('watchlist_item_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['group_id'], ['groups.id'],
            name='fk_group_member_group', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['watchlist_item_id'], ['watchlist_items.id'],
            name='fk_group_member_item', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'watchlist_item_id', name='uq_group_member'),
    )
    with op.batch_alter_table('group_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_group_members_group_id'), ['group_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_group_members_watchlist_item_id'), ['watchlist_item_id'], unique=False)


def downgrade():
    with op.batch_alter_table('group_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_group_members_watchlist_item_id'))
        batch_op.drop_index(batch_op.f('ix_group_members_group_id'))
    op.drop_table('group_members')

    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_groups_user_id'))
    op.drop_table('groups')
