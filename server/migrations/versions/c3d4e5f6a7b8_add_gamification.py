"""add gamification: points, user_achievements, user_flair

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-26 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('points', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('flair_selected', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('show_flair', sa.Boolean(), server_default='1', nullable=False))

    op.create_table(
        'user_achievements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ladder_key', sa.String(), nullable=False),
        sa.Column('tier', sa.Integer(), nullable=False),
        sa.Column('earned_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_achievement_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'ladder_key', 'tier', name='uq_user_ladder_tier'),
    )
    with op.batch_alter_table('user_achievements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_achievements_user_id'), ['user_id'], unique=False)

    op.create_table(
        'user_flair',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('flair_key', sa.String(), nullable=False),
        sa.Column('purchased_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_flair_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'flair_key', name='uq_user_flair'),
    )
    with op.batch_alter_table('user_flair', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_flair_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_flair', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_flair_user_id'))
    op.drop_table('user_flair')
    with op.batch_alter_table('user_achievements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_achievements_user_id'))
    op.drop_table('user_achievements')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('show_flair')
        batch_op.drop_column('flair_selected')
        batch_op.drop_column('points')
