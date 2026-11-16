"""Add additive tender source registry policy and provenance linkage.

This migration creates no tenants, no source profiles, and does not alter any
legacy provenance.  Every existing tender_source_provenance row keeps a NULL
registry_source_id until an explicitly authorized internal association exists.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# The existing alembic_version.version_num column is VARCHAR(32).
revision = "tender_source_registry_v1"
down_revision = "tender_intelligence_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tender_source_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_category", sa.String(32), nullable=False),
        sa.Column("permitted_ingestion_method", sa.String(32), nullable=False),
        sa.Column("supports_discovery", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_document_retrieval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_revision_tracking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_data_classification", sa.String(32), nullable=False),
        sa.Column("enabled_for_tender_ingestion", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authorization_evidence_reference", sa.String(1024), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_id", name="uq_tender_source_profile_source"),
        sa.CheckConstraint("source_category IN ('CPPP','IREPS','GEM','STATE_EPROCUREMENT','MANUAL_UPLOAD','OTHER')", name="ck_tender_source_profile_category"),
        sa.CheckConstraint("permitted_ingestion_method IN ('MANUAL_UPLOAD','OFFICIAL_API','LICENSED_FEED','OFFICIAL_DOCUMENT','FIXTURE_TEST')", name="ck_tender_source_profile_ingestion"),
        sa.CheckConstraint("default_data_classification IN ('AUTHENTIC','DEMO','FIXTURE_TEST')", name="ck_tender_source_profile_classification"),
    )
    op.create_index("ix_tender_source_profiles_source_id", "tender_source_profiles", ["source_id"])
    op.create_index("ix_tender_source_profiles_enabled_for_tender_ingestion", "tender_source_profiles", ["enabled_for_tender_ingestion"])
    op.add_column("tender_source_provenance", sa.Column("registry_source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_tender_source_provenance_registry_source", "tender_source_provenance", "market_sources", ["registry_source_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tender_source_provenance_registry_source_id", "tender_source_provenance", ["registry_source_id"])


def downgrade() -> None:
    op.drop_index("ix_tender_source_provenance_registry_source_id", table_name="tender_source_provenance")
    op.drop_constraint("fk_tender_source_provenance_registry_source", "tender_source_provenance", type_="foreignkey")
    op.drop_column("tender_source_provenance", "registry_source_id")
    op.drop_index("ix_tender_source_profiles_enabled_for_tender_ingestion", table_name="tender_source_profiles")
    op.drop_index("ix_tender_source_profiles_source_id", table_name="tender_source_profiles")
    op.drop_table("tender_source_profiles")
