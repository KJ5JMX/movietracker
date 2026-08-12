"""guard against double-crediting a coin purchase

A partial unique index on coin_ledger.ref WHERE reason = 'purchase' makes it
impossible for the same App Store transaction id to be credited twice, even if
two verify-coins requests race past the "already credited?" lookup before
either commits. Partial (not a plain unique) because other ledger reasons
legitimately reuse refs: two users buying the same avatar both write
reason='spend', ref='<avatar key>'.

Revision ID: a9c3e5b1d7f2
Revises: f7a2b3c4d5e6
Create Date: 2026-08-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9c3e5b1d7f2'
down_revision = 'f7a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        'uq_coin_ledger_purchase_ref',
        'coin_ledger',
        ['ref'],
        unique=True,
        sqlite_where=sa.text("reason = 'purchase'"),
        postgresql_where=sa.text("reason = 'purchase'"),
    )


def downgrade():
    op.drop_index('uq_coin_ledger_purchase_ref', table_name='coin_ledger')
