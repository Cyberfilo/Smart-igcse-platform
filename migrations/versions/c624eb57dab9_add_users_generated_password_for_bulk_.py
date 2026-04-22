"""add users.generated_password for bulk credential export

Revision ID: c624eb57dab9
Revises: bcc14a2ee084
Create Date: 2026-04-22 11:21:46.843930

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c624eb57dab9'
down_revision = 'bcc14a2ee084'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('generated_password', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('generated_password')
