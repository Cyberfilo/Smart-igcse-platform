"""add revision_list_items table for user-curated revision queue (+ branch merge)

Revision ID: 9d1a72c4a0f1
Revises: 04ecaa67ad79, e1f3a87b2d40
Create Date: 2026-04-27 09:30:00.000000

This revision serves a dual purpose: it adds the new revision_list_items
table AND merges two pre-existing parallel heads into a single chain. The
heads were 04ecaa67ad79 (V/S/D learning-style scores + SR overlay) and
e1f3a87b2d40 (users.current_password / must_change_password). Both declared
down_revision='c624eb57dab9', creating a fork. Earlier deploys tolerated
the branched state because only one head was unapplied at a time; this
revision makes the chain linear again so future migrations don't trip on
"Multiple head revisions are present".
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d1a72c4a0f1'
# Tuple = merge revision. Both prior heads must be applied before this runs.
down_revision = ('04ecaa67ad79', 'e1f3a87b2d40')
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
