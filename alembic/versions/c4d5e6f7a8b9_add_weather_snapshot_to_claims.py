"""add weather snapshot to claims

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a8b9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('claims') as batch_op:
        batch_op.add_column(sa.Column('weather_rainfall', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('weather_temp',     sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('weather_aqi',      sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('claims') as batch_op:
        batch_op.drop_column('weather_aqi')
        batch_op.drop_column('weather_temp')
        batch_op.drop_column('weather_rainfall')
