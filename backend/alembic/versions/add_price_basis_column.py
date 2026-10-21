"""add price_basis column to price_observations

Revision ID: add_price_basis
Revises: 3e7ab5ad494b
Create Date: 2026-10-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_price_basis'
down_revision = '3e7ab5ad494b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add price_basis column with default value
    op.add_column('price_observations',
                  sa.Column('price_basis', sa.String(length=32), nullable=False, server_default='EX_WORKS'))
    # Create index on price_basis
    op.create_index(op.f('ix_price_observations_price_basis'), 'price_observations', ['price_basis'], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f('ix_price_observations_price_basis'), table_name='price_observations')
    # Drop column
    op.drop_column('price_observations', 'price_basis')
