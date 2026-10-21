"""market price alert rules and events

Revision ID: market_price_alerts
Revises: market_ingestion_foundation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "market_price_alerts"
down_revision = "market_ingestion_foundation"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("market_price_alert_rules", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
      sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
      sa.Column("material_form", sa.String(32), nullable=False), sa.Column("grade", sa.String(64), nullable=False), sa.Column("region", sa.String(64), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("unit", sa.String(16), nullable=False), sa.Column("price_basis", sa.String(32), nullable=False), sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("price_sources.id", ondelete="RESTRICT")), sa.Column("price_condition", sa.String(8), nullable=False), sa.Column("price_threshold", sa.Numeric(20,4)), sa.Column("movement_threshold_pct", sa.Numeric(12,6)), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.CheckConstraint("price_condition IN ('ABOVE','BELOW')", name="ck_market_alert_condition"))
    for column in ("organization_id", "user_id", "material_form", "source_id", "is_active"): op.create_index(f"ix_market_price_alert_rules_{column}", "market_price_alert_rules", [column])
    op.create_table("market_price_alert_events", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("alert_rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_price_alert_rules.id", ondelete="CASCADE"), nullable=False), sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("price_observations.id", ondelete="CASCADE"), nullable=False), sa.Column("notification_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False), sa.Column("trigger_type", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("alert_rule_id", "observation_id", name="uq_market_alert_event_observation"))
    for column in ("organization_id", "alert_rule_id", "observation_id", "notification_id"): op.create_index(f"ix_market_price_alert_events_{column}", "market_price_alert_events", [column])

def downgrade() -> None:
    op.drop_table("market_price_alert_events")
    op.drop_table("market_price_alert_rules")
