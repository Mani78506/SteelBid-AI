"""restore timestamp defaults for legacy tender workflow tables

Revision ID: workflow_timestamp_defaults
Revises: jayraj_tender_discovery_metadata
"""
from alembic import op
import sqlalchemy as sa


revision = "workflow_timestamp_defaults"
down_revision = "jayraj_tender_discovery_metadata"
branch_labels = None
depends_on = None


TABLES = ("tender_workflows", "tender_requirement_snapshots", "bom_versions", "bom_items")


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", existing_type=sa.DateTime(timezone=True),
                        server_default=sa.text("now()"), existing_nullable=False)
        op.alter_column(table, "updated_at", existing_type=sa.DateTime(timezone=True),
                        server_default=sa.text("now()"), existing_nullable=False)


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "updated_at", existing_type=sa.DateTime(timezone=True),
                        server_default=None, existing_nullable=False)
        op.alter_column(table, "created_at", existing_type=sa.DateTime(timezone=True),
                        server_default=None, existing_nullable=False)
