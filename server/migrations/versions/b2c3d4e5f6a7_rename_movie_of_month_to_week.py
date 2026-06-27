"""rename Movie of the Month -> Movie of the Week

Renames the tables and period column. Battles are unaffected (still monthly via
their voting window).

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-06-26 02:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table('movies_of_month', 'movies_of_week')
    with op.batch_alter_table('movies_of_week', schema=None) as batch_op:
        batch_op.alter_column('month_key', new_column_name='week_key')

    op.rename_table('movie_of_month_completions', 'movie_of_week_completions')
    with op.batch_alter_table('movie_of_week_completions', schema=None) as batch_op:
        batch_op.alter_column('motm_id', new_column_name='mow_id')


def downgrade():
    with op.batch_alter_table('movie_of_week_completions', schema=None) as batch_op:
        batch_op.alter_column('mow_id', new_column_name='motm_id')
    op.rename_table('movie_of_week_completions', 'movie_of_month_completions')

    with op.batch_alter_table('movies_of_week', schema=None) as batch_op:
        batch_op.alter_column('week_key', new_column_name='month_key')
    op.rename_table('movies_of_week', 'movies_of_month')
