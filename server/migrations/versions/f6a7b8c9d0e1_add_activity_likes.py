"""add activity_likes (thumbs-up on friend discovery activity)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-29 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'activity_likes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_activity_like_user'),
        sa.ForeignKeyConstraint(['item_id'], ['watchlist_items.id'], name='fk_activity_like_item'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'item_id', name='uq_activity_like_user_item'),
    )
    with op.batch_alter_table('activity_likes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_activity_likes_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_activity_likes_item_id'), ['item_id'], unique=False)


def downgrade():
    with op.batch_alter_table('activity_likes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_activity_likes_item_id'))
        batch_op.drop_index(batch_op.f('ix_activity_likes_user_id'))
    op.drop_table('activity_likes')
