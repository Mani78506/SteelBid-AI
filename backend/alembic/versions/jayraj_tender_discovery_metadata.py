"""add tender discovery provenance metadata

Revision ID: jayraj_tender_discovery_metadata
Revises: tender_workflow_orchestration
"""
from alembic import op
import sqlalchemy as sa


revision = "jayraj_tender_discovery_metadata"
down_revision = "tender_workflow_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenders", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tenders", sa.Column("data_classification", sa.String(length=32), nullable=False, server_default="OPERATIONAL"))
    op.add_column("tenders", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="USER_UPLOAD"))
    op.add_column("tenders", sa.Column("original_source_url", sa.String(length=1000), nullable=True))
    op.add_column("tenders", sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenders", sa.Column("rate_approval_status", sa.String(length=32), nullable=False, server_default="NOT_APPLICABLE"))
    op.create_index("ix_tenders_data_classification", "tenders", ["data_classification"])


def downgrade() -> None:
    op.drop_index("ix_tenders_data_classification", table_name="tenders")
    op.drop_column("tenders", "rate_approval_status")
    op.drop_column("tenders", "publication_date")
    op.drop_column("tenders", "original_source_url")
    op.drop_column("tenders", "source_type")
    op.drop_column("tenders", "data_classification")
    op.drop_column("tenders", "is_demo")
