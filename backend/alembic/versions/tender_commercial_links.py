"""add explicit tender commercial links

Revision ID: tender_commercial_links
Revises: add_price_basis
"""
from alembic import op
import sqlalchemy as sa

revision = "tender_commercial_links"
down_revision = "add_price_basis"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("cost_estimates", sa.Column("tender_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_cost_estimates_tender", "cost_estimates", "tenders", ["tender_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_cost_estimates_tender_id", "cost_estimates", ["tender_id"])
    op.add_column("quotations", sa.Column("tender_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_quotations_tender", "quotations", "tenders", ["tender_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_quotations_tender_id", "quotations", ["tender_id"])

def downgrade() -> None:
    op.drop_index("ix_quotations_tender_id", table_name="quotations")
    op.drop_constraint("fk_quotations_tender", "quotations", type_="foreignkey")
    op.drop_column("quotations", "tender_id")
    op.drop_index("ix_cost_estimates_tender_id", table_name="cost_estimates")
    op.drop_constraint("fk_cost_estimates_tender", "cost_estimates", type_="foreignkey")
    op.drop_column("cost_estimates", "tender_id")
