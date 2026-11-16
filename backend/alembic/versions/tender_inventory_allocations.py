"""Add auditable tender inventory allocations (reviewed, unapplied).

Revision ID: tender_inventory_allocations
Revises: workflow_timestamp_defaults
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "tender_inventory_allocations"
down_revision = "workflow_timestamp_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("tender_inventory_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bom_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bom_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bom_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stock_lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stock_lots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(20,6), nullable=False), sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("valuation_rate", sa.Numeric(20,4), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("valuation_source", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_tender_inventory_allocations_bom_item_id", "tender_inventory_allocations", ["bom_item_id"])


def downgrade() -> None:
    op.drop_table("tender_inventory_allocations")
