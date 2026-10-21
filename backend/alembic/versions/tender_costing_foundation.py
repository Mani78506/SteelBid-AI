"""add tender requirement snapshots and supplier selections

Revision ID: tender_costing_foundation
Revises: tender_commercial_links
"""
from alembic import op
import sqlalchemy as sa

revision = "tender_costing_foundation"
down_revision = "tender_commercial_links"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("tender_requirement_snapshots", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("organization_id", sa.UUID(), nullable=False), sa.Column("tender_id", sa.UUID(), nullable=False), sa.Column("source_boq_item_id", sa.UUID(), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("material_id", sa.UUID(), nullable=False), sa.Column("form", sa.String(32)), sa.Column("grade", sa.String(64)), sa.Column("specification", sa.JSON(), nullable=False, server_default="{}"), sa.Column("quantity", sa.Numeric(20, 6), nullable=False), sa.Column("unit", sa.String(16), nullable=False), sa.Column("wastage_pct", sa.Numeric(8, 6), nullable=False, server_default="0"), sa.Column("engineering_status", sa.String(16), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["source_boq_item_id"], ["boq_items.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["material_id"], ["organization_materials.id"], ondelete="RESTRICT"), sa.UniqueConstraint("tender_id", "version", "source_boq_item_id", name="uq_tender_req_snapshot"))
    op.create_index("ix_tender_requirement_snapshots_tender_id", "tender_requirement_snapshots", ["tender_id"])
    op.create_table("tender_supplier_selections", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("organization_id", sa.UUID(), nullable=False), sa.Column("tender_id", sa.UUID(), nullable=False), sa.Column("tender_requirement_snapshot_id", sa.UUID(), nullable=False), sa.Column("supplier_quote_id", sa.UUID(), nullable=False), sa.Column("selected_qty", sa.Numeric(20, 6), nullable=False), sa.Column("unit", sa.String(16), nullable=False), sa.Column("unit_price", sa.Numeric(20, 4), nullable=False), sa.Column("freight_per_unit", sa.Numeric(20, 4), nullable=False, server_default="0"), sa.Column("nonrecoverable_tax_per_unit", sa.Numeric(20, 4), nullable=False, server_default="0"), sa.Column("landed_cost_per_unit", sa.Numeric(20, 4), nullable=False), sa.Column("valid_until", sa.Date()), sa.Column("delivery_terms", sa.String(128)), sa.Column("status", sa.String(16), nullable=False, server_default="SELECTED"), sa.Column("selected_by", sa.UUID()), sa.Column("cancellation_reason", sa.String(500)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["tender_requirement_snapshot_id"], ["tender_requirement_snapshots.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supplier_quote_id"], ["supplier_quotes.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["selected_by"], ["users.id"]), sa.UniqueConstraint("tender_requirement_snapshot_id", "supplier_quote_id", name="uq_tender_supplier_selection"))
    op.create_index("ix_tender_supplier_selections_tender_id", "tender_supplier_selections", ["tender_id"])

def downgrade() -> None:
    op.drop_table("tender_supplier_selections")
    op.drop_table("tender_requirement_snapshots")
