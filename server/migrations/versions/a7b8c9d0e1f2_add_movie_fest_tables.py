"""add ShelfMates Movie Fest tables (movie of the month + battles)

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-26 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'movies_of_month',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('month_key', sa.String(), nullable=False),
        sa.Column('imdb_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('year', sa.String(), nullable=True),
        sa.Column('poster', sa.String(), nullable=True),
        sa.Column('media_type', sa.String(), server_default='movie', nullable=False),
        sa.Column('blurb', sa.String(), nullable=True),
        sa.Column('streaming', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('month_key'),
    )

    op.create_table(
        'movie_of_month_completions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('motm_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('review', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['motm_id'], ['movies_of_month.id'], name='fk_motm_completion_motm'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_motm_completion_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('motm_id', 'user_id', name='uq_motm_user'),
    )
    with op.batch_alter_table('movie_of_month_completions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_movie_of_month_completions_motm_id'), ['motm_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_movie_of_month_completions_user_id'), ['user_id'], unique=False)

    op.create_table(
        'battles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('a_imdb_id', sa.String(), nullable=False),
        sa.Column('a_title', sa.String(), nullable=False),
        sa.Column('a_year', sa.String(), nullable=True),
        sa.Column('a_poster', sa.String(), nullable=True),
        sa.Column('a_streaming', sa.Text(), nullable=True),
        sa.Column('b_imdb_id', sa.String(), nullable=False),
        sa.Column('b_title', sa.String(), nullable=False),
        sa.Column('b_year', sa.String(), nullable=True),
        sa.Column('b_poster', sa.String(), nullable=True),
        sa.Column('b_streaming', sa.Text(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'battle_votes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('battle_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('choice', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['battle_id'], ['battles.id'], name='fk_battle_vote_battle'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_battle_vote_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('battle_id', 'user_id', name='uq_battle_user'),
    )
    with op.batch_alter_table('battle_votes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_battle_votes_battle_id'), ['battle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_battle_votes_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('battle_votes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_battle_votes_user_id'))
        batch_op.drop_index(batch_op.f('ix_battle_votes_battle_id'))
    op.drop_table('battle_votes')
    op.drop_table('battles')
    with op.batch_alter_table('movie_of_month_completions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_movie_of_month_completions_user_id'))
        batch_op.drop_index(batch_op.f('ix_movie_of_month_completions_motm_id'))
    op.drop_table('movie_of_month_completions')
    op.drop_table('movies_of_month')
