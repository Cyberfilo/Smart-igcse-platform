"""expand learning-style fields: V/S/D scores + SR overlay

Revision ID: 04ecaa67ad79
Revises: c624eb57dab9
Create Date: 2026-04-22 12:03:16.292132
"""
from alembic import op
import sqlalchemy as sa


revision = '04ecaa67ad79'
down_revision = 'c624eb57dab9'
branch_labels = None
depends_on = None


def upgrade():
    # sr_overlay is NOT NULL — we need server_default so existing rows land on False.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('learning_style_scores', sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column('sr_overlay', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.alter_column(
            'learning_style_profile',
            existing_type=sa.VARCHAR(length=32),
            type_=sa.String(length=40),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'learning_style_profile',
            existing_type=sa.String(length=40),
            type_=sa.VARCHAR(length=32),
            existing_nullable=True,
        )
        batch_op.drop_column('sr_overlay')
        batch_op.drop_column('learning_style_scores')
