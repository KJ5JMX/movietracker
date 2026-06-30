"""add night_messages (Movie Night chat)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-27 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'night_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['movie_night_sessions.id'], name='fk_night_message_session'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_night_message_user'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('night_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_night_messages_session_id'), ['session_id'], unique=False)


def downgrade():
    with op.batch_alter_table('night_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_night_messages_session_id'))
    op.drop_table('night_messages')
