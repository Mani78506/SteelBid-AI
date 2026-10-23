"""add tenant scoped tender workflow links

Revision ID: tender_workflow_orchestration
Revises: global_commodity_benchmarks
"""
from alembic import op
import sqlalchemy as sa

revision = "tender_workflow_orchestration"
down_revision = "global_commodity_benchmarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bom_versions", sa.Column("tender_id", sa.UUID(), nullable=True))
    op.add_column("bom_versions", sa.Column("requirement_snapshot_version", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_bom_versions_tender", "bom_versions", "tenders", ["tender_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_bom_versions_tender_id", "bom_versions", ["tender_id"])
    op.add_column("bom_items", sa.Column("tender_requirement_snapshot_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_bom_items_requirement_snapshot", "bom_items", "tender_requirement_snapshots", ["tender_requirement_snapshot_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_bom_items_tender_requirement_snapshot_id", "bom_items", ["tender_requirement_snapshot_id"])
    op.create_table(
        "tender_workflows",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("tender_id", sa.UUID(), nullable=False),
        sa.Column("requirement_snapshot_version", sa.Integer(), nullable=True),
        sa.Column("bom_version_id", sa.UUID(), nullable=True),
        sa.Column("cost_estimate_id", sa.UUID(), nullable=True),
        sa.Column("quotation_id", sa.UUID(), nullable=True),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("use_demo_commercial_rates", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submission_status", sa.String(24), nullable=False, server_default="NOT_READY"),
        sa.Column("external_submission_reference", sa.String(128), nullable=True),
        sa.Column("external_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submission_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bom_version_id"], ["bom_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cost_estimate_id"], ["cost_estimates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quotation_id"], ["quotations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "tender_id", name="uq_tender_workflow"),
    )
    for name, column in (("ix_tender_workflows_tender_id", "tender_id"), ("ix_tender_workflows_bom_version_id", "bom_version_id"), ("ix_tender_workflows_cost_estimate_id", "cost_estimate_id"), ("ix_tender_workflows_quotation_id", "quotation_id"), ("ix_tender_workflows_customer_id", "customer_id"), ("ix_tender_workflows_submission_status", "submission_status")):
        op.create_index(name, "tender_workflows", [column])


def downgrade() -> None:
    op.drop_table("tender_workflows")
    op.drop_index("ix_bom_items_tender_requirement_snapshot_id", table_name="bom_items")
    op.drop_constraint("fk_bom_items_requirement_snapshot", "bom_items", type_="foreignkey")
    op.drop_column("bom_items", "tender_requirement_snapshot_id")
    op.drop_index("ix_bom_versions_tender_id", table_name="bom_versions")
    op.drop_constraint("fk_bom_versions_tender", "bom_versions", type_="foreignkey")
    op.drop_column("bom_versions", "requirement_snapshot_version")
    op.drop_column("bom_versions", "tender_id")
