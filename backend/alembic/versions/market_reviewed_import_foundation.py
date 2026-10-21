"""reviewed market import persistence foundation

Revision ID: market_reviewed_import
Revises: tender_costing_foundation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "market_reviewed_import"
down_revision = "tender_costing_foundation"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("market_sources", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("provenance_classification", sa.String(32), nullable=False), sa.Column("reference_url", sa.String(2048)), sa.Column("document_reference", sa.String(512)), sa.Column("attribution_text", sa.String(1000), nullable=False), sa.Column("license_status", sa.String(32), nullable=False), sa.Column("usage_restrictions", sa.String(2000)), sa.Column("publication_frequency", sa.String(64)), sa.Column("visibility", sa.String(24), nullable=False, server_default="OWNER_ONLY"), sa.Column("redistribution_permitted", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("organization_id", "name", name="uq_market_source_org_name"), sa.CheckConstraint("license_status IN ('PENDING','APPROVED','RESTRICTED','EXPIRED')", name="ck_market_source_license"), sa.CheckConstraint("visibility IN ('OWNER_ONLY','ENTITLED','GLOBAL')", name="ck_market_source_visibility"))
    op.create_index("ix_market_sources_organization_id", "market_sources", ["organization_id"])
    op.create_table("market_import_batches", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_sources.id", ondelete="RESTRICT"), nullable=False), sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"), sa.Column("file_name", sa.String(512)), sa.Column("import_key", sa.String(128), nullable=False), sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"), sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"), sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"), sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT")), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.CheckConstraint("status IN ('DRAFT','VALIDATED','PENDING_APPROVAL','APPROVED','REJECTED')", name="ck_market_import_batch_status"), sa.UniqueConstraint("organization_id", "import_key", name="uq_market_import_batch_org_key"))
    for c in ("organization_id","source_id","uploaded_by","status"): op.create_index(f"ix_market_import_batches_{c}", "market_import_batches", [c])
    op.create_table("market_import_staged_rows", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_import_batches.id", ondelete="CASCADE"), nullable=False), sa.Column("row_number", sa.Integer(), nullable=False), sa.Column("original_data", postgresql.JSONB(), nullable=False, server_default="{}"), sa.Column("normalized_data", postgresql.JSONB(), nullable=False, server_default="{}"), sa.Column("validation_errors", postgresql.JSONB(), nullable=False, server_default="[]"), sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"), sa.Column("dedupe_key", sa.String(128)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("batch_id","row_number",name="uq_market_import_row"), sa.CheckConstraint("status IN ('DRAFT','VALID','INVALID','DUPLICATE','COMMITTED')", name="ck_market_import_row_status"))
    for c in ("batch_id","status","dedupe_key"): op.create_index(f"ix_market_import_staged_rows_{c}", "market_import_staged_rows", [c])

def downgrade() -> None:
    op.drop_table("market_import_staged_rows")
    op.drop_table("market_import_batches")
    op.drop_table("market_sources")
