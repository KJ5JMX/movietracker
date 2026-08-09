"""add profile_banner to users

Revision ID: f7a2b3c4d5e6
Revises: e6f1a2b3c4d5
Create Date: 2026-08-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a2b3c4d5e6'
down_revision = 'e6f1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('profile_banner', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('profile_banner')
