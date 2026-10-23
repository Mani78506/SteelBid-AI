"""market source ingestion provenance foundation

Revision ID: market_source_ingest
Revises: market_price_alerts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "market_source_ingest"
down_revision = "market_price_alerts"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("market_source_documents", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_sources.id", ondelete="CASCADE"), nullable=False), sa.Column("original_document_url", sa.String(2048), nullable=False), sa.Column("publisher", sa.String(255), nullable=False), sa.Column("document_title", sa.String(512), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("reporting_period", sa.String(128)), sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False), sa.Column("sha256_checksum", sa.String(64), nullable=False), sa.Column("parser_version", sa.String(64)), sa.Column("reuse_basis", sa.String(1000)), sa.Column("extraction_status", sa.String(24), nullable=False, server_default="PENDING"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("source_id", "sha256_checksum", name="uq_market_source_document_checksum"))
    for c in ("source_id", "published_at", "extraction_status"): op.create_index(f"ix_market_source_documents_{c}", "market_source_documents", [c])
    op.create_table("market_source_extractions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_source_documents.id", ondelete="CASCADE"), nullable=False), sa.Column("parser_version", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False), sa.Column("error_summary", sa.String(2000)), sa.Column("records_found", sa.Integer(), nullable=False, server_default="0"), sa.Column("records_accepted", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("source_document_id", "parser_version", name="uq_market_source_extraction_parser"))
    op.create_index("ix_market_source_extractions_source_document_id", "market_source_extractions", ["source_document_id"])
    op.create_table("market_source_refresh_states", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_sources.id", ondelete="CASCADE"), nullable=False), sa.Column("last_checked_at", sa.DateTime(timezone=True)), sa.Column("last_success_at", sa.DateTime(timezone=True)), sa.Column("latest_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_source_documents.id", ondelete="SET NULL")), sa.Column("etag", sa.String(512)), sa.Column("last_modified", sa.String(512)), sa.Column("latest_checksum", sa.String(64)), sa.Column("error_state", sa.String(2000)), sa.Column("next_scheduled_check", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("source_id", name="uq_market_source_refresh_source"))
    op.create_index("ix_market_source_refresh_states_next_scheduled_check", "market_source_refresh_states", ["next_scheduled_check"])
    op.add_column("price_observations", sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_source_documents.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_price_observations_source_document_id", "price_observations", ["source_document_id"])

def downgrade():
    op.drop_index("ix_price_observations_source_document_id", table_name="price_observations"); op.drop_column("price_observations", "source_document_id")
    op.drop_table("market_source_refresh_states"); op.drop_table("market_source_extractions"); op.drop_table("market_source_documents")
