"""Add persisted tender extraction metadata, provenance and evidence-based revisions.

This migration is intentionally authored only.  It has not been applied to any
database by this change.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "tender_intelligence_foundation"
down_revision = "tender_submission_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tender_documents", sa.Column("processing_status", sa.String(32), nullable=False, server_default="PENDING"))
    op.add_column("tender_documents", sa.Column("content_checksum", sa.String(64), nullable=True))
    op.add_column("tender_documents", sa.Column("parser_version", sa.String(64), nullable=True))
    op.add_column("tender_documents", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tender_documents_processing_status", "tender_documents", ["processing_status"])
    op.create_index("ix_tender_documents_content_checksum", "tender_documents", ["content_checksum"])
    op.create_table("tender_source_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_name", sa.String(255), nullable=False), sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("official_source_url", sa.String(2048)), sa.Column("external_tender_reference", sa.String(255)), sa.Column("provider_record_id", sa.String(255)),
        sa.Column("authorization_status", sa.String(32), nullable=False, server_default="UNVERIFIED"), sa.Column("authorization_evidence_reference", sa.String(1024)),
        sa.Column("data_classification", sa.String(32), nullable=False, server_default="DEMO"),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True)), sa.Column("last_retrieved_at", sa.DateTime(timezone=True)), sa.Column("last_successfully_checked_at", sa.DateTime(timezone=True)),
        sa.Column("normalized_payload_checksum", sa.String(64)), sa.Column("source_status", sa.String(32), nullable=False, server_default="PENDING"), sa.Column("retrieval_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "provider_name", "provider_record_id", name="uq_tender_source_provider_record"))
    op.create_index("ix_tender_source_provenance_tender_id", "tender_source_provenance", ["tender_id"])
    op.create_table("tender_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_provenance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tender_source_provenance.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(32), nullable=False), sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("previous_value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("new_value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("related_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tender_documents.id", ondelete="SET NULL")), sa.Column("document_checksum", sa.String(64)), sa.Column("evidence_reference", sa.String(2048)), sa.Column("evidence_page_ref", sa.String(128)),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="PENDING_REVIEW"), sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")), sa.Column("acknowledged_at", sa.DateTime(timezone=True)), sa.Column("event_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "source_provenance_id", "event_fingerprint", name="uq_tender_revision_event"))
    op.create_index("ix_tender_revisions_tender_id", "tender_revisions", ["tender_id"])
    op.create_index("ix_tender_revisions_source_provenance_id", "tender_revisions", ["source_provenance_id"])


def downgrade() -> None:
    op.drop_table("tender_revisions")
    op.drop_table("tender_source_provenance")
    op.drop_index("ix_tender_documents_content_checksum", table_name="tender_documents")
    op.drop_index("ix_tender_documents_processing_status", table_name="tender_documents")
    op.drop_column("tender_documents", "processed_at")
    op.drop_column("tender_documents", "parser_version")
    op.drop_column("tender_documents", "content_checksum")
    op.drop_column("tender_documents", "processing_status")
