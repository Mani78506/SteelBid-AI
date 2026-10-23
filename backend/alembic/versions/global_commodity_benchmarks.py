"""separate public commodity benchmarks from price observations

Revision ID: global_commodity_benchmarks
Revises: market_source_claims
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "global_commodity_benchmarks"
down_revision = "market_source_claims"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("global_commodity_benchmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_source_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("commodity_name", sa.String(128), nullable=False), sa.Column("original_unit", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False), sa.Column("price_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False), sa.Column("external_record_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "source_document_id", "commodity_name", "observed_on", name="uq_global_benchmark_document_point"))
    op.create_index("ix_global_benchmark_org_observed", "global_commodity_benchmarks", ["organization_id", "observed_on"])

def downgrade():
    op.drop_index("ix_global_benchmark_org_observed", table_name="global_commodity_benchmarks")
    op.drop_table("global_commodity_benchmarks")
