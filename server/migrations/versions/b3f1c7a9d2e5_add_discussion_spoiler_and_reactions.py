"""add is_spoiler to discussion_comments and discussion_reactions table

Revision ID: b3f1c7a9d2e5
Revises: f7a1e9c3d2b4
Create Date: 2026-08-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f1c7a9d2e5'
down_revision = 'f7a1e9c3d2b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('discussion_comments', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_spoiler',
                sa.Boolean(),
                nullable=False,
                server_default='0',
            )
        )

    op.create_table(
        'discussion_reactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('comment_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('emoji', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['comment_id'], ['discussion_comments.id'],
            name='fk_discussion_reaction_comment', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name='fk_discussion_reaction_user',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'comment_id', 'user_id', 'emoji', name='uq_discussion_reaction'
        ),
    )
    with op.batch_alter_table('discussion_reactions', schema=None) as batch_op:
        batch_op.create_index(
            'ix_discussion_reactions_comment_id', ['comment_id'], unique=False
        )
        batch_op.create_index(
            'ix_discussion_reactions_user_id', ['user_id'], unique=False
        )


def downgrade():
    with op.batch_alter_table('discussion_reactions', schema=None) as batch_op:
        batch_op.drop_index('ix_discussion_reactions_user_id')
        batch_op.drop_index('ix_discussion_reactions_comment_id')
    op.drop_table('discussion_reactions')

    with op.batch_alter_table('discussion_comments', schema=None) as batch_op:
        batch_op.drop_column('is_spoiler')
