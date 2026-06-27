"""add streaming availability reports

Crowdsourced "where to watch" data: one row per (imdb_id, country, platform)
with a freshness timestamp users can confirm or flag-removed.

Revision ID: f1a2b3c4d5e6
Revises: e5f9a2b7c1d8
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e5f9a2b7c1d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'streaming_availability_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('imdb_id', sa.String(), nullable=False),
        sa.Column('country', sa.String(), server_default='US', nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('reported_by_user_id', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('confirm_count', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_confirmed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['reported_by_user_id'], ['users.id'],
            name='fk_streaming_report_user',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'imdb_id', 'country', 'platform',
            name='uq_report_title_country_platform',
        ),
    )
    with op.batch_alter_table('streaming_availability_reports', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_streaming_availability_reports_imdb_id'),
            ['imdb_id'], unique=False,
        )


def downgrade():
    with op.batch_alter_table('streaming_availability_reports', schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f('ix_streaming_availability_reports_imdb_id')
        )
    op.drop_table('streaming_availability_reports')
