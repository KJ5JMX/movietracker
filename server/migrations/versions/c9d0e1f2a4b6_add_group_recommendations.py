"""add group_recommendations (send a whole collection to a friend)

Revision ID: c9d0e1f2a4b6
Revises: b8c9d0e1f2a4
Create Date: 2026-07-03 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a4b6'
down_revision = 'b8c9d0e1f2a4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'group_recommendations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('from_user_id', sa.Integer(), nullable=False),
        sa.Column('to_user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('items', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], name='fk_group_rec_from_user'),
        sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], name='fk_group_rec_to_user'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('group_recommendations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_group_recommendations_from_user_id'), ['from_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_group_recommendations_to_user_id'), ['to_user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('group_recommendations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_group_recommendations_to_user_id'))
        batch_op.drop_index(batch_op.f('ix_group_recommendations_from_user_id'))
    op.drop_table('group_recommendations')
