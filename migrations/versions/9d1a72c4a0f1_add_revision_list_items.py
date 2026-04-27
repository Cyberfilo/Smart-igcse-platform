"""add revision_list_items table for user-curated revision queue

Revision ID: 9d1a72c4a0f1
Revises: e1f3a87b2d40
Create Date: 2026-04-27 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d1a72c4a0f1'
down_revision = 'e1f3a87b2d40'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'revision_list_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name='fk_revlist_topic_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_revlist_user_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'topic_id', name='uq_revlist_user_topic'),
    )
    op.create_index(
        'ix_revision_list_items_user_id',
        'revision_list_items',
        ['user_id'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_revision_list_items_user_id', table_name='revision_list_items')
    op.drop_table('revision_list_items')
