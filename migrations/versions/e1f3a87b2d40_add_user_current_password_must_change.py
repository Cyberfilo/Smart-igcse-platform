"""add users.current_password + users.must_change_password for OTP rotation

Revision ID: e1f3a87b2d40
Revises: c624eb57dab9
Create Date: 2026-04-22 14:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f3a87b2d40'
down_revision = 'c624eb57dab9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('current_password', sa.String(length=64), nullable=True))
        # server_default false so the ALTER TABLE backfills existing rows
        # (single live admin at time of writing) to "already rotated" —
        # otherwise they'd be frozen out on next login.
        batch_op.add_column(sa.Column(
            'must_change_password',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('must_change_password')
        batch_op.drop_column('current_password')
