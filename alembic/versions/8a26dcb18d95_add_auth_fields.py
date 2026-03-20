"""add_auth_fields

Revision ID: 8a26dcb18d95
Revises: d101e4c9e05d
Create Date: 2026-03-20 00:03:29.222513

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a26dcb18d95'
down_revision: Union[str, Sequence[str], None] = 'd101e4c9e05d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workers', sa.Column('username', sa.String(), nullable=True))
    op.add_column('workers', sa.Column('password', sa.String(), nullable=True))
    op.add_column('workers', sa.Column('email', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('workers', 'email')
    op.drop_column('workers', 'password')
    op.drop_column('workers', 'username')
