"""add_grace_period_and_fraud_score

Revision ID: f3c9a1d72e44
Revises: 8a26dcb18d95
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f3c9a1d72e44'
down_revision: Union[str, Sequence[str], None] = '8a26dcb18d95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('policies', sa.Column('grace_period_end', sa.DateTime(), nullable=True))
    op.add_column('claims',   sa.Column('fraud_score', sa.Float(), nullable=True, server_default='0.0'))


def downgrade() -> None:
    op.drop_column('claims',   'fraud_score')
    op.drop_column('policies', 'grace_period_end')
