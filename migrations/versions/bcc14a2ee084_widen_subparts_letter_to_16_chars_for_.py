"""widen subparts.letter to 16 chars for nested letters like a(i)

Revision ID: bcc14a2ee084
Revises: 2a401a7c19d2
Create Date: 2026-04-22 10:45:06.936573

"""
from alembic import op
import sqlalchemy as sa


revision = 'bcc14a2ee084'
down_revision = '2a401a7c19d2'
branch_labels = None
depends_on = None


def upgrade():
    # Nested subpart letters go up to roughly 'a(iii)' (6 chars) in practice;
    # 16 gives ample headroom for any future notation without paying for it.
    with op.batch_alter_table('subparts', schema=None) as batch_op:
        batch_op.alter_column(
            'letter',
            existing_type=sa.String(length=4),
            type_=sa.String(length=16),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table('subparts', schema=None) as batch_op:
        batch_op.alter_column(
            'letter',
            existing_type=sa.String(length=16),
            type_=sa.String(length=4),
            existing_nullable=False,
        )
