"""add pro coin economy: coins, pro_avatars shop, coin_ledger, user_avatar pool

Revision ID: e6f1a2b3c4d5
Revises: d5e6f7a8b9c0
Create Date: 2026-08-08 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f1a2b3c4d5'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('coins', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('coin_signup_bonus_granted', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('coin_last_monthly_grant', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('coin_gift_last_grant', sa.DateTime(), nullable=True))

    with op.batch_alter_table('user_avatars', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pool', sa.String(), server_default='free', nullable=False))

    op.create_table(
        'pro_avatars',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('image_full_data', sa.Text(), nullable=False),
        sa.Column('image_head_data', sa.Text(), nullable=False),
        sa.Column('coin_price', sa.Integer(), nullable=False),
        sa.Column('artist_credit', sa.String(), nullable=True),
        sa.Column('slot', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', name='uq_pro_avatar_key'),
    )

    op.create_table(
        'coin_ledger',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('ref', sa.String(), nullable=True),
        sa.Column('balance_after', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_coin_ledger_user'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('coin_ledger', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_coin_ledger_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('coin_ledger', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_coin_ledger_user_id'))
    op.drop_table('coin_ledger')
    op.drop_table('pro_avatars')

    with op.batch_alter_table('user_avatars', schema=None) as batch_op:
        batch_op.drop_column('pool')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('coin_gift_last_grant')
        batch_op.drop_column('coin_last_monthly_grant')
        batch_op.drop_column('coin_signup_bonus_granted')
        batch_op.drop_column('coins')
