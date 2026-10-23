"""persistent market source provider configuration

Revision ID: market_source_provider_cfg
Revises: market_source_ingest
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="market_source_provider_cfg"
down_revision="market_source_ingest"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("market_source_provider_configs", sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("source_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("market_sources.id",ondelete="CASCADE"),nullable=False),sa.Column("provider_id",sa.String(64),nullable=False),sa.Column("provider_type",sa.String(32),nullable=False),sa.Column("enabled",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("endpoint_url",sa.String(2048)),sa.Column("fixture_reference",sa.String(128)),sa.Column("credential_reference",sa.String(255)),sa.Column("access_authorized",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("reuse_authorized",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("parser_id",sa.String(64),nullable=False,server_default="fixture-csv"),sa.Column("parser_version",sa.String(64),nullable=False,server_default="fixture-csv-v1"),sa.Column("refresh_interval_seconds",sa.Integer(),nullable=False,server_default="3600"),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.UniqueConstraint("source_id",name="uq_market_source_provider_config_source"))
    op.create_index("ix_market_source_provider_configs_enabled","market_source_provider_configs",["enabled"]); op.create_index("ix_market_source_provider_configs_provider_id","market_source_provider_configs",["provider_id"])
def downgrade(): op.drop_table("market_source_provider_configs")
