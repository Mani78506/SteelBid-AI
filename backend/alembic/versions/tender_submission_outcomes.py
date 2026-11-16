"""Add immutable-audited tender submission and outcome records (unapplied)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "tender_submission_outcomes"
down_revision = "tender_inventory_allocations"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("tender_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quotation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quotations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quotation_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quotation_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("submission_method", sa.String(64)), sa.Column("portal_reference", sa.String(128)), sa.Column("acknowledgment_reference", sa.String(128)),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tender_documents.id", ondelete="RESTRICT")),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")), sa.Column("submitted_at", sa.DateTime(timezone=True)), sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("outcome_status", sa.String(16)), sa.Column("outcome_date", sa.Date()), sa.Column("outcome_reference", sa.String(128)), sa.Column("outcome_value", sa.Numeric(20,4)), sa.Column("outcome_currency", sa.String(3)), sa.Column("outcome_remarks", sa.Text()),
        sa.Column("parent_submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tender_submissions.id", ondelete="RESTRICT")), sa.Column("correction_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_tender_submissions_tender_id", "tender_submissions", ["tender_id"])
    op.create_index("ix_tender_submissions_status", "tender_submissions", ["status"])
    op.create_index("ix_tender_submissions_parent_submission_id", "tender_submissions", ["parent_submission_id"])

def downgrade() -> None:
    op.drop_index("ix_tender_submissions_status", table_name="tender_submissions")
    op.drop_index("ix_tender_submissions_parent_submission_id", table_name="tender_submissions")
    op.drop_index("ix_tender_submissions_tender_id", table_name="tender_submissions")
    op.drop_table("tender_submissions")
