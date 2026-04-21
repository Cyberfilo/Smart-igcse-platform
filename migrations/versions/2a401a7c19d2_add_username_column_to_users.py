"""add username column to users

Revision ID: 2a401a7c19d2
Revises: 2cf78e4c2f0e
Create Date: 2026-04-21 14:58:35.498656

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a401a7c19d2'
down_revision = '2cf78e4c2f0e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('username', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint('uq_users_username', ['username'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_username', type_='unique')
        batch_op.drop_column('username')
