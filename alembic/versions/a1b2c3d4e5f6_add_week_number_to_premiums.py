"""add_week_number_to_premiums

Revision ID: a1b2c3d4e5f6
Revises: f3c9a1d72e44
Create Date: 2025-01-02 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f3c9a1d72e44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('premiums', sa.Column('week_number', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('premiums', 'week_number')
