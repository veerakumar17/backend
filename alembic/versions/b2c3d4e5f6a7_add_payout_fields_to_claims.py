"""add payout fields to claims

Revision ID: b2c3d4e5f6a7
Revises: f3c9a1d72e44
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('claims') as batch_op:
        batch_op.add_column(sa.Column('payout_status', sa.String(), nullable=True, server_default='pending'))
        batch_op.add_column(sa.Column('payout_transaction_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('payout_processed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('claims') as batch_op:
        batch_op.drop_column('payout_processed_at')
        batch_op.drop_column('payout_transaction_id')
        batch_op.drop_column('payout_status')
