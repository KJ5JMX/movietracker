"""add chapter progress and discussion comments

Revision ID: b7d3e9a1c2f4
Revises: a1b9c4f2d7e3
Create Date: 2026-06-12 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d3e9a1c2f4'
down_revision = 'a1b9c4f2d7e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('watchlist_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chapter_progress', sa.Integer(), nullable=True))

    op.create_table(
        'discussion_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('imdb_id', sa.String(), nullable=False),
        sa.Column('media_type', sa.String(), server_default='book', nullable=False),
        sa.Column('chapter', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_discussion_comment_user'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discussion_comments_user_id', 'discussion_comments', ['user_id'])
    op.create_index('ix_discussion_item', 'discussion_comments', ['imdb_id', 'media_type'])


def downgrade():
    op.drop_index('ix_discussion_item', table_name='discussion_comments')
    op.drop_index('ix_discussion_comments_user_id', table_name='discussion_comments')
    op.drop_table('discussion_comments')
    with op.batch_alter_table('watchlist_items', schema=None) as batch_op:
        batch_op.drop_column('chapter_progress')
