"""market ingestion provider run history

Revision ID: market_ingestion_foundation
Revises: market_reviewed_import
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "market_ingestion_foundation"
down_revision = "market_reviewed_import"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("price_observations", sa.Column("external_observation_id", sa.String(255), nullable=True))
    op.create_index("ix_price_observations_external_observation_id", "price_observations", ["external_observation_id"])
    op.create_table("market_ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("price_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider_key", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.String(2000)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "provider_key", "idempotency_key", name="uq_market_ingestion_run_key"),
        sa.CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED','PARTIAL','SKIPPED')", name="ck_market_ingestion_run_status"))
    for column in ("organization_id", "source_id", "provider_key", "status"):
        op.create_index(f"ix_market_ingestion_runs_{column}", "market_ingestion_runs", [column])

def downgrade() -> None:
    op.drop_table("market_ingestion_runs")
    op.drop_index("ix_price_observations_external_observation_id", table_name="price_observations")
    op.drop_column("price_observations", "external_observation_id")
